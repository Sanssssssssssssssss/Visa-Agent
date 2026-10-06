"""Replay three natural-language, staged document handovers with the real API.

This checks the application and ZIP locally. Provider receipt/download evidence
is a separate result in docs/full-delivery.md; this script does not send email.
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", choices=["visitor", "student", "skilled_worker"], nargs="+")
    parser.add_argument("--formatted", action="store_true", help="Use labelled JPEG/scan layouts instead of legacy field fixtures")
    parser.add_argument("--materials", type=Path, help="Versioned input directory for --formatted")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise ValueError("Use a new output directory to preserve earlier runs")
    starts = {
        "visitor": "你好，我想去英国旅游，第一次办签证，不知道从哪里开始。",
        "student": "你好，我拿到英国学校的录取了，要办学生签证，需要准备些什么？",
        "skilled_worker": "Hi, I have a job offer in the UK and need a Skilled Worker visa. What should I send you first?",
    }
    plans = []
    for route, text in starts.items():
        if args.only and route not in args.only:
            continue
        base = (args.materials or ROOT / "datasets/formatted-materials-v2") / route if args.formatted else ROOT / "datasets/materials" / f"dev_{route}"
        identity = base / ("identity.jpg" if args.formatted else "identity.pdf")
        remainder = ([base / name for name in {"visitor":["funds-scan.pdf", "work.jpg"],
                     "student":["funds-scan.pdf", "health.jpg", "school.jpg"],
                     "skilled_worker":["health.jpg", "language.jpg", "sponsor-scan.pdf"]}[route]] if args.formatted else
                     [p for p in sorted(base.glob("*.pdf")) if p.name != "identity.pdf"])
        plans.append({"id": route, "events": [
            {"text": text, "attachments": [], "expected": "WAIT_USER"},
            {"text": "表填好了，先发护照给你，其他的我再整理一下。" if route != "skilled_worker" else
                     "I have filled in the form and attached my passport. I will send the other documents shortly.",
             "attachments": [str(ROOT / "datasets/intake" / f"{route}-example-TEST-ONLY.xlsx"), str(identity)], "expected": "WAIT_USER"},
            {"text": "剩下这几份也找齐了，帮我看看还缺什么？" if route != "skilled_worker" else
                     "Here are the remaining documents. Is anything still missing?",
             "attachments": [str(p) for p in remainder], "expected": "COMPLETE"},
        ]})
    paths = {Path(p) for plan in plans for event in plan["events"] for p in event["attachments"]}
    write_json(out / "experiment.json", {"synthetic": True, "email_transport": False, "cap": None, "plans": plans,
        "input_hashes": {str(p.resolve().relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
        "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (ROOT / "src/visa_agent").rglob("*") if p.suffix in {".py", ".md"}}})
    budget = LiveBudget(out / "live-budget.sqlite3")
    reports = []
    for plan in plans:
        started = time.monotonic()
        service = VisaService(out / plan["id"], "live", hitl=False, application_forms=True, budget=budget)
        service.create_case(plan["id"], test_mode=True)
        turns, failures = [], []
        for index, event in enumerate(plan["events"]):
            # Reopen persisted state each turn, as with a restarted inbox process.
            service = VisaService(out / plan["id"], "live", hitl=False, application_forms=True, budget=budget)
            incoming = CaseEvent(case_id=plan["id"], event_id=str(index), text=event["text"], attachments=event["attachments"])
            result = service.handle_event(incoming)
            passed = not result.error and result.status == event["expected"]
            if index == 1:
                passed &= result.form_path is None and "填写 C 列" not in result.reply and "Fill column C" not in result.reply
            if result.status == Status.COMPLETE:
                verify_pack(service.store.get(plan["id"]))
            before = budget.count()
            duplicate = service.handle_event(incoming)
            passed &= duplicate.duplicate and before == budget.count()
            turns.append({"input": event, "result": result.model_dump(mode="json"), "passed": bool(passed)})
            if not passed:
                failures.append(index)
            print(json.dumps({"route": plan["id"], "turn": index + 1, "status": result.status, "passed": bool(passed),
                              "requests": budget.count()}, ensure_ascii=False), flush=True)
            if result.error:
                break
        traces = service.store.traces(plan["id"])
        usage = {key: sum(t.get("usage", {}).get(key, 0) for t in traces) for key in ("requests", "input_tokens", "output_tokens")}
        reports.append({"id": plan["id"], "passed": not failures, "failures": failures, "turns": turns, "usage": usage,
                        "seconds": round(time.monotonic() - started, 3), "models": sorted({t["model"] for t in traces if "model" in t})})
        write_json(out / "traces" / (plan["id"] + ".json"), traces)
        write_json(out / "summary.json", {"passed": sum(r["passed"] for r in reports), "cases": len(reports),
            "http_requests": budget.count(), "usage": {k: sum(r["usage"][k] for r in reports) for k in usage},
            "price_configured": False, "results": reports})


if __name__ == "__main__":
    main()
