"""Freeze public-file inputs, then run bounded real-model repetitions.

Usage: python scripts/stress_public_materials.py prepare
       python scripts/stress_public_materials.py run --count 3
       python scripts/stress_public_materials.py run
Each completed row is retained. A resumed batch skips it, including failures.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time

import pypdfium2 as pdfium

from visa_agent.agent import LiveBudget
from visa_agent.evidence import normalized
from visa_agent.service import VisaService
from visa_agent.types import CaseEvent

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "datasets/public-stress.json"
OUT = ROOT / "output/public-stress"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare():
    if (OUT / "frozen.json").exists():
        raise ValueError("Inputs already frozen; use another --output for a new experiment")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    entries = {entry["id"]: entry for entry in spec["documents"]}
    for entry in entries.values():
        if sha(ROOT / entry["path"]) != entry["sha256"]:
            raise ValueError(f"Source changed: {entry['path']}")
    jobs = []
    for run in spec["runs"]:
        entry = entries[run["document"]]
        path = ROOT / entry["path"]
        if run["variant"] != "original":
            images = []
            with pdfium.PdfDocument(path) as pdf:
                for i in range(len(pdf)):
                    page = pdf[i]
                    bitmap = page.render(scale=2)
                    images.append(bitmap.to_pil().convert("RGB"))
                    bitmap.close()
                    page.close()
            target = OUT / "inputs" / f"{entry['id']}-{run['variant']}"
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                if run["variant"] == "scan":
                    path = target.with_suffix(".pdf")
                    images[0].save(path, "PDF", save_all=True, append_images=images[1:], resolution=144)
                else:
                    path = target.with_suffix(".jpg")
                    with images[0].rotate(2, expand=True, fillcolor="white") as tilted:
                        tilted.save(path, quality=90)
            finally:
                for image in images:
                    image.close()
        for repeat in range(1, run["repeats"] + 1):
            jobs.append({"id": f"{entry['id']}-{run['variant']}-{repeat}",
                         "document": entry["id"], "variant": run["variant"],
                         "path": str(path.relative_to(ROOT)), "sha256": sha(path)})
    # Run one original of each document first, before spending on repetitions.
    jobs.sort(key=lambda j: (not (j["variant"] == "original" and j["id"].endswith("-1")), j["id"]))
    ledger = ROOT / "data/live-budget.sqlite3"
    initial = LiveBudget(ledger).count()
    write(OUT / "frozen.json", {"created_at": datetime.now(timezone.utc).isoformat(),
          "spec_hash": sha(SPEC), "jobs": jobs, "ledger_start": initial,
          "ledger_limit": min(60, initial + 24), "request_cap": 24})
    print(f"Frozen {len(jobs)} runs; ledger starts at {initial}, stops at {min(60, initial + 24)}", flush=True)


def summarize(rows, frozen):
    signatures = {}
    for row in rows:
        if row["variant"] == "original":
            signatures.setdefault(row["document"], set()).add(json.dumps(
                row["accepted_fields"], ensure_ascii=False, sort_keys=True))
    times = sorted(row["seconds"] for row in rows)
    return {"requested_runs": len(frozen["jobs"]), "completed_runs": len(rows),
            "contract_passes": sum(row["passed"] for row in rows),
            "requests": sum(row["usage"].get("requests", 0) for row in rows),
            "input_tokens": sum(row["usage"].get("input_tokens", 0) for row in rows),
            "output_tokens": sum(row["usage"].get("output_tokens", 0) for row in rows),
            "usage_incomplete": any(row["usage_incomplete"] for row in rows),
            "median_seconds": round(statistics.median(times), 3) if times else None,
            "max_seconds": max(times) if times else None,
            "distinct_field_sets_per_original": {k: len(v) for k, v in signatures.items()},
            "note": "Contract pass allows safe omissions; see each row's extracted and omitted fields. No approval is performed. Serial robustness experiment, not a production throughput benchmark.",
            "reports": rows}


def run(count):
    frozen = json.loads((OUT / "frozen.json").read_text(encoding="utf-8"))
    if sha(SPEC) != frozen["spec_hash"]:
        raise ValueError("Expected answers changed after freeze")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    entries = {entry["id"]: entry for entry in spec["documents"]}
    budget = LiveBudget(ROOT / "data/live-budget.sqlite3", frozen["ledger_limit"])
    service = VisaService(OUT / "cases", "live", budget=budget)
    rows = []
    pending = []
    for job in frozen["jobs"]:
        path = OUT / "runs" / (job["id"] + ".json")
        if path.exists():
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        else:
            pending.append(job)
    for job in pending[:count]:
        if budget.count() >= budget.limit:
            print("Request limit reached; remaining runs not executed", flush=True)
            break
        path = ROOT / job["path"]
        if sha(path) != job["sha256"]:
            raise ValueError(f"Input changed: {path}")
        entry = entries[job["document"]]
        case_id = "public-" + job["id"]
        try:
            service.store.get(case_id)
        except ValueError:
            service.store.create(case_id)
        event = CaseEvent(case_id=case_id, event_id="upload", kind="upload",
                          text=spec["message"], attachments=[str(path)])
        start = time.monotonic()
        result = service.handle_event(event)
        duration = round(time.monotonic() - start, 3)
        case = service.store.get(case_id)
        trace = service.store.traces(case_id)[-1]
        fields = {}
        for fact in case.facts:
            if fact.active:
                fields.setdefault(fact.key, []).append(fact.value)
        fields = {k: sorted(set(v)) for k, v in sorted(fields.items())}
        allowed = {**spec["common_allowed_facts"], **entry["allowed_facts"]}
        wrong = {key: values for key, values in fields.items() if any(
            normalized(value) not in {normalized(v) for v in allowed.get(key, [])} for value in values)}
        text = "\n".join(p.text for d in case.documents for p in d.pages)
        missing_markers = [m for m in entry["markers"] if normalized(m) not in normalized(text)]
        checks = {
            "no_service_error": not result.error,
            "no_false_readiness": case.status.value in {"WAIT_USER", "NEEDS_HUMAN"},
            "no_approval_or_pack": case.approval is None and case.pack_path is None,
            "body_read": not missing_markers,
            "classification": bool(case.documents) and all(d.kind in entry["allowed_kinds"] for d in case.documents),
            "no_wrong_accepted_fields": not wrong,
        }
        # Replay an identical event using a fresh service to exercise persistence and dedup.
        checks["restart_duplicate"] = False
        if not result.error:
            usage_before = budget.count()
            restarted = VisaService(OUT / "cases", "live", budget=budget)
            duplicate = restarted.handle_event(event)
            checks["restart_duplicate"] = (duplicate.duplicate and duplicate.version == result.version
                                           and budget.count() == usage_before)
        row = {**job, "case_id": case_id, "seconds": duration,
               "prompt_version": trace.get("prompt_version"),
               "source_hashes": {p: sha(ROOT / p) for p in (
                   "src/visa_agent/documents.py", "src/visa_agent/agent.py", "src/visa_agent/evidence.py")},
               "result": result.model_dump(mode="json"), "checks": checks,
               "passed": all(checks.values()), "accepted_fields": fields,
               "wrong_fields": wrong, "missing_markers": missing_markers,
               "omitted_fields": sorted(set(entry["allowed_facts"]) - fields.keys()),
               "problems": [p for d in case.documents for p in d.problems],
               "rejected_candidates": trace.get("rejected_candidates", []),
               "usage": trace.get("usage", {}), "usage_incomplete": trace.get("usage_incomplete", False)}
        write(OUT / "runs" / (job["id"] + ".json"), row)
        write(OUT / "traces" / (job["id"] + ".json"), service.store.traces(case_id))
        rows.append(row)
        write(OUT / "summary.json", summarize(rows, frozen))
        print(json.dumps({"id": job["id"], "passed": row["passed"], "seconds": duration,
                          "requests": row["usage"].get("requests"), "wrong": wrong,
                          "error": result.error}, ensure_ascii=False), flush=True)
    summary = summarize(rows, frozen)
    write(OUT / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run"])
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    OUT = args.output.resolve()
    if args.action == "prepare":
        prepare()
    else:
        summary = run(args.count)
        if summary["contract_passes"] != summary["completed_runs"]:
            raise SystemExit(1)
