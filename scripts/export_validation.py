"""Export this synthetic experiment only; never export arbitrary local cases."""
import hashlib
import argparse
import json
from pathlib import Path
import shutil
import sqlite3

from visa_agent.delivery import build_pack, verify_pack
from visa_agent.store import Store, write_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/legacy-validation")
    out = parser.parse_args().output
    out.mkdir(parents=True, exist_ok=True)
    store = Store(ROOT / "data")
    case_ids = []
    for name, source in {
        "live": "output/live-v1/summary.json",
        "smoke": "output/smoke/summary.json",
        "offline": "output/offline/summary.json",
        "compatibility": "output/compatibility.json",
        "compatibility-incomplete-attempt": "output/compatibility-incomplete-attempt.json",
        "materials": "output/material-compatibility.json",
    }.items():
        data = json.loads((ROOT / source).read_text(encoding="utf-8"))
        (out / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str).replace(
                str(ROOT).replace("\\", "\\\\"), "<REPO>"), encoding="utf-8")
        if name in {"live", "smoke"}:
            case_ids.extend(r["case_id"] for r in data["reports"])
        if name == "materials":
            case_ids.append(data["case_id"])
    for case_id in case_ids:
        if not case_id.startswith(("dev_", "holdout_", "material-compatibility")):
            raise ValueError("Refusing to export a non-fixture case")
        trace = json.dumps(store.traces(case_id), ensure_ascii=False, indent=2, default=str)
        (out / f"trace-{case_id}.json").write_text(
            trace.replace(str(ROOT).replace("\\", "\\\\"), "<REPO>"), encoding="utf-8")
    with sqlite3.connect(ROOT / "data/live-budget.sqlite3") as db:
        calls = [{"id": row[0], "at_utc": row[1], "model": row[2]}
                 for row in db.execute("SELECT id,at,model FROM calls ORDER BY id")]
    live = json.loads((out / "live.json").read_text(encoding="utf-8"))
    totals = {key: sum(r["usage"][key] for r in live["reports"])
              for key in ("input_tokens", "output_tokens", "requests")}
    write_json(out / "usage.json", {
        "reserved_http_requests": len(calls), "limit": 60, "ledger": calls,
        "formal_six_cases": totals, "cost_usd": None,
        "note": "Prices not configured. One initial successful plain-reply probe lost token accounting when SDK usage() changed to usage; one 400 response has no usage. All reserved requests remain counted.",
    })
    sample = store.get(live["reports"][0]["case_id"])
    build_pack(sample, store.root)  # Refresh presentation only; manifest and approval unchanged.
    verify_pack(sample)
    shutil.copyfile(sample.pack_path, out / "sample-visitor.zip")
    files = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
             for base in ("src", "scripts", "tests") for p in (ROOT / base).rglob("*.py")}
    for name in ("uv.lock", "pyproject.toml", "datasets/freeze.json"):
        files[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    write_json(out / "code-and-data-hashes.json", files)
    print(f"Exported {len(case_ids)} synthetic case traces; formal usage: {totals}")


if __name__ == "__main__":
    main()
