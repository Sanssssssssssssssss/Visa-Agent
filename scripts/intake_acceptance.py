"""Finite real-API acceptance with frozen workbook bytes and no cumulative call cap.

Uses actual PDFs, model responses, SQLite and ZIPs. Email transport is simulated
here; separately recorded SMTP/IMAP receipts demonstrate provider delivery.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from visa_agent.agent import LiveBudget
from visa_agent.delivery import verify_pack
from visa_agent.service import VisaService
from visa_agent.store import write_json
from visa_agent.types import CaseEvent, Status

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets"


def scenarios():
    result = []
    starts = {"visitor": "您好，我想去英国旅游，第一次申请，请一步步指导。",
              "student": "你好，我要申请英国学生签证，该从哪里开始？",
              "skilled_worker": "Hello, I need a UK Skilled Worker visa. Please guide me step by step."}
    for route, text in starts.items():
        files = [DATA / "intake" / f"{route}-example-TEST-ONLY.xlsx", *sorted((DATA / "materials" / f"dev_{route}").glob("*.pdf"))]
        result.append({"id": route, "demo": True, "events": [(text, [], "WAIT_USER"),
            ("这些是填好的表格和材料，请检查。" if route != "skilled_worker" else "Here are my completed worksheet and documents. Please check them.", files, "COMPLETE")]})
    docs = sorted((DATA / "materials" / "dev_visitor").glob("*.pdf"))
    for bad in ("missing-birthday", "invalid-email", "formula", "passport-conflict", "prompt-injection"):
        events = [(starts["visitor"], [], "WAIT_USER"),
                  ("请检查附件。", [DATA / "intake" / f"bad-{bad}.xlsx", *docs] if bad != "prompt-injection" else [DATA / "intake" / f"bad-{bad}.xlsx"], "NOT_COMPLETE")]
        if bad in {"missing-birthday", "invalid-email"}:
            events.append(("已修改表格，请重新检查。", [DATA / "intake" / "visitor-example-TEST-ONLY.xlsx"], "COMPLETE"))
        result.append({"id": bad, "demo": True, "events": events})
    result.append({"id": "sample-real-case", "demo": False, "events": [(starts["visitor"], [], "WAIT_USER"),
        ("请检查这些文件。", [DATA / "intake" / "visitor-example-TEST-ONLY.xlsx", *docs], "NOT_COMPLETE")]})
    result.append({"id": "language-switch", "demo": False, "events": [
        ("你好，我第一次申请，不知道从哪里开始。", [], "WAIT_USER"),
        ("Thank you", [], "WAIT_USER"), ("请用中文回复。", [], "WAIT_USER")]})
    result.append({"id": "injection-with-documents", "demo": True, "events": [
        ("Hello, I need a Standard Visitor visa.", [], "WAIT_USER"),
        ("Please check the worksheet and all documents.", [DATA / "intake/bad-prompt-injection.xlsx", *docs], "NOT_COMPLETE")]})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/intake/live-v1")
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    out = args.output.resolve()
    plans = [s for s in scenarios() if not args.only or s["id"] in args.only]
    snapshot = {"source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "src/visa_agent").rglob("*") if p.suffix in {".py", ".md"}},
        "dataset_sha256": hashlib.sha256((DATA / "intake/manifest.json").read_bytes()).hexdigest(),
        "scenarios": plans, "cap": None}
    frozen = out / "experiment.json"
    if frozen.exists():
        raise ValueError("Use a new output folder; prior experiments are retained")
    write_json(frozen, snapshot)
    manifest = json.loads((DATA / "intake/manifest.json").read_text())
    for name, expected in manifest["files"].items():
        if hashlib.sha256((DATA / "intake" / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Changed fixture: " + name)
    budget = LiveBudget(out / "live-budget.sqlite3")
    reports = []
    for spec in plans:
        service = VisaService(out / spec["id"], "live", hitl=False, application_forms=True, budget=budget)
        service.create_case(spec["id"], test_mode=spec["demo"])
        started, turns, failures = time.monotonic(), [], []
        for index, (text, files, expected) in enumerate(spec["events"]):
            event = CaseEvent(case_id=spec["id"], event_id=f"e{index}", text=text, attachments=[str(p) for p in files])
            result = service.handle_event(event)
            case = service.store.get(spec["id"])
            passed = not result.error and (result.status != Status.COMPLETE if expected == "NOT_COMPLETE" else result.status == expected)
            if spec["id"] == "language-switch":
                passed &= case.language == ("en" if index == 1 else "zh")
                passed &= ("visiting, studying or working" in result.reply if index == 1 else "旅游、读书还是工作" in result.reply)
            if not passed:
                failures.append(f"turn{index}:{result.status}:{result.error}")
            if result.pack_path:
                verify_pack(case)
            before = budget.count()
            duplicate = service.handle_event(event)
            if not duplicate.duplicate or budget.count() != before:
                failures.append("duplicate_reprocessed")
            turns.append({**result.model_dump(mode="json"), "expected": expected, "passed": bool(passed)})
            print(json.dumps({"case": spec["id"], "turn": index, "status": result.status,
                "passed": bool(passed), "requests": budget.count(), "error": result.error}, ensure_ascii=False), flush=True)
            if result.error:
                break
            # Reopen SQLite for each turn to exercise restart continuity.
            service = VisaService(out / spec["id"], "live", hitl=False, application_forms=True, budget=budget)
        traces = service.store.traces(spec["id"])
        usage = {k: sum(t.get("usage", {}).get(k, 0) for t in traces) for k in ("requests", "input_tokens", "output_tokens")}
        report = {"id": spec["id"], "passed": not failures, "failures": failures, "turns": turns,
            "usage": usage, "seconds": round(time.monotonic()-started, 3), "models": sorted({t["model"] for t in traces if "model" in t})}
        reports.append(report)
        write_json(out / "runs" / f"{spec['id']}.json", report)
        write_json(out / "traces" / f"{spec['id']}.json", traces)
        write_json(out / "summary.json", {"cases": len(reports), "passed": sum(r["passed"] for r in reports),
            "http_requests": budget.count(), "usage": {k: sum(r["usage"][k] for r in reports) for k in usage},
            "price_configured": False, "results": reports})


if __name__ == "__main__":
    main()
