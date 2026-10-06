"""SQLite transactions and a small event inbox. Files and full traces stay local."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time

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
        for attempt in range(8):
            try:
                self._initialize()
                break
            except sqlite3.OperationalError as exc:
                # Concurrent first-start workers can race on WAL's exclusive lock.
                if "locked" not in str(exc) or attempt == 7:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def _initialize(self):
        with self.connect() as db:
            if db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                    case_id TEXT NOT NULL, event_id TEXT NOT NULL,
                    input_hash TEXT NOT NULL, body TEXT NOT NULL,
                    status TEXT NOT NULL, result TEXT, error TEXT,
                    PRIMARY KEY(case_id,event_id),
                    FOREIGN KEY(case_id) REFERENCES cases(id));
                CREATE TABLE IF NOT EXISTS runs(
                    run_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS inbox_sessions(
                    id TEXT PRIMARY KEY, channel TEXT NOT NULL, account TEXT NOT NULL,
                    thread TEXT NOT NULL, sender TEXT NOT NULL, state TEXT NOT NULL,
                    case_id TEXT NOT NULL REFERENCES cases(id));
                CREATE TABLE IF NOT EXISTS inbox_deliveries(
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, input_hash TEXT NOT NULL,
                    case_id TEXT NOT NULL, result TEXT);
                CREATE TABLE IF NOT EXISTS web_workspaces(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=120)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        # ponytail: one SQLite writer serializes all cases, including model calls.
        # For concurrent servers, replace with per-case leases; CLI throughput is intentionally low.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def create(self, case_id: str, *, test_mode=False, hitl_enabled=True, application_forms=False) -> Case:
        from .types import CaseEvent
        CaseEvent(case_id=case_id, event_id="validate")
        case = Case(id=case_id, test_mode=test_mode, hitl_enabled=hitl_enabled, application_forms=application_forms)
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

    def dialogue(self, case_id: str, *, limit=100, before=None):
        """Paged durable transcript; Case.history is only the recent working window."""
        if not 1 <= limit <= 100:
            raise ValueError("History limit must be 1..100")
        with self.connect() as db:
            rows = db.execute("SELECT rowid,body,result FROM events WHERE case_id=? AND result IS NOT NULL "
                              "AND rowid < ? ORDER BY rowid DESC LIMIT ?",
                              (case_id, before or 2**63-1, limit)).fetchall()
        return [{"cursor": r["rowid"], "input": json.loads(r["body"]), "result": json.loads(r["result"])}
                for r in reversed(rows)]
