"""Real-model partial Student receipt, follow-up and CAS handover; no mail sent."""
import argparse
from pathlib import Path

from visa_agent.conversation import material_progress
from visa_agent.delivery import verify_pack
from visa_agent.service import VisaService
from visa_agent.store import write_json
from visa_agent.types import CaseEvent

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output directory to preserve prior receipts")
    app = VisaService(args.output, "live", hitl=False, application_forms=True)
    app.create_case("student", test_mode=True)
    base = ROOT / "datasets/formatted-materials-v2/student"
    steps = [
        ("我要办学生签证，填好的信息表、护照、资金证明和结核检查都附上了，请看看还差什么。",
         [ROOT / "datasets/intake/student-example-TEST-ONLY.xlsx", base / "identity.jpg",
          base / "funds-scan.pdf", base / "health.jpg"]),
        ("我明明给了三份材料，为什么只算两份？资金证明的PDF我已经发了呀。", []),
        ("学校的CAS也补上了，请帮我整理最后的材料包。", [base / "school.jpg"]),
    ]
    rows = []
    for index, (text, files) in enumerate(steps):
        result = app.handle_event(CaseEvent(case_id="student", event_id=str(index), text=text,
                                           attachments=[str(p) for p in files]))
        case = app.store.get("student")
        progress = material_progress(case)
        finance = next(c for c in case.checks if c.id == "finance")
        complete = index == 2
        passed = (not result.error and finance.status == ("pass" if complete else "unknown")
                  and progress["received"] == (4 if complete else 3)
                  and progress["checked"] == (4 if complete else 2)
                  and result.status == ("COMPLETE" if complete else "WAIT_USER"))
        if result.status == "COMPLETE":
            verify_pack(case)
        trace = app.store.traces("student")[-1]
        rows.append({"turn": index, "input": text, "files": [p.name for p in files],
                     "status": result.status, "received": progress["received"], "checked": progress["checked"],
                     "total": progress["total"], "finance": finance.model_dump(), "reply": result.reply,
                     "error": result.error, "usage": trace.get("usage", {}), "passed": passed})
        write_json(args.output / "summary.json", {"passed": sum(r["passed"] for r in rows),
            "turns": len(rows), "usage": {k: sum(r["usage"].get(k, 0) for r in rows)
            for k in ("requests", "input_tokens", "output_tokens")}, "results": rows})
        print(f"turn={index} status={result.status} received={progress['received']} checked={progress['checked']} passed={passed}", flush=True)
    if not all(r["passed"] for r in rows):
        raise SystemExit("Receipt regression failed; inspect summary.json and local traces")


if __name__ == "__main__":
    main()
