"""SQLite transactions and a small event inbox. Files and full traces stay local."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3

from .types import Case, now_utc


def digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


class Store:
    def __init__(self, root: Path | str = "data"):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "cases.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                    case_id TEXT NOT NULL, event_id TEXT NOT NULL,
                    input_hash TEXT NOT NULL, body TEXT NOT NULL,
                    status TEXT NOT NULL, result TEXT, error TEXT,
                    PRIMARY KEY(case_id,event_id),
                    FOREIGN KEY(case_id) REFERENCES cases(id));
                CREATE TABLE IF NOT EXISTS runs(
                    run_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, body TEXT NOT NULL);
            """)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=120)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def transaction(self):
        # ponytail: one SQLite writer serializes all cases, including model calls.
        # For concurrent servers, replace with per-case leases; CLI throughput is intentionally low.
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create(self, case_id: str) -> Case:
        from .types import CaseEvent
        CaseEvent(case_id=case_id, event_id="validate")
        case = Case(id=case_id)
        with self.transaction() as db:
            db.execute("INSERT INTO cases VALUES (?,?)", (case.id, case.model_dump_json()))
        return case

    def get(self, case_id: str, db=None) -> Case:
        if db is None:
            with self.connect() as connection:
                return self.get(case_id, connection)
        row = db.execute("SELECT body FROM cases WHERE id=?", (case_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown case: {case_id}")
        return Case.model_validate_json(row[0])

    @staticmethod
    def save(case: Case, db) -> None:
        db.execute("UPDATE cases SET body=? WHERE id=?", (case.model_dump_json(), case.id))

    def record_run(self, case_id: str, run_id: str, trace: dict, db=None):
        trace = {"run_id": run_id, "case_id": case_id, "recorded_at": now_utc(), **trace}
        if db is None:
            with self.transaction() as connection:
                self.record_run(case_id, run_id, trace, connection)
            return
        db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?)",
                   (run_id, case_id, json.dumps(trace, ensure_ascii=False, default=str)))

    def traces(self, case_id: str) -> list[dict]:
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(
                "SELECT body FROM runs WHERE case_id=? ORDER BY rowid", (case_id,))]

    def events(self, case_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM events WHERE case_id=? ORDER BY rowid", (case_id,))]
