"""Apply the separately frozen semantic review to all runs, including retained failures."""

import json
from pathlib import Path

from visa_agent.agent import LiveBudget
from visa_agent.delivery import verify_pack
from visa_agent.store import Store, write_json

ROOT = Path(__file__).resolve().parents[1]


def summarize():
    out = ROOT / "output/customer-service-v1"
    spec = json.loads((ROOT / "datasets/customer-service/semantic-checks.json").read_text(encoding="utf-8"))
    summary, receipts = [], []
    store = Store(out / "cases")
    for path in sorted((out / "runs").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        traces = json.loads((out / "traces" / path.name).read_text(encoding="utf-8"))
        checks = spec["checks"].get(row["scenario"], {})
        failed = []
        last = traces[-1]["after"]
        if "route" in checks and last["route"] != checks["route"]:
            failed.append("stated_route_omitted")
        if "forbidden_reply" in checks and checks["forbidden_reply"] in row["results"][-1]["reply"]:
            failed.append("repeated_known_question")
        progress = [p["checked"] for p in row["progress_by_turn"]]
        if "progress" in checks and progress != checks["progress"]:
            failed.append("expected_progress_not_reached")
        if checks.get("absent_nationality") and row["fields"].get("nationality"):
            failed.append("nationality_inferred")
        summary.append({"id": row["id"], "application_checks": row["passed"], "application_failures": row["failures"],
                        "semantic_checks": not failed, "semantic_failures": failed,
                        "state": row["status"], "progress": progress, "usage": row["usage"],
                        "duplicate_checks": len(row["redeliveries"]),
                        "duplicate_failures": sum(not r["passed"] for r in row["redeliveries"])})
        if row["status"] == "READY_FOR_REVIEW":
            import zipfile
            case = store.get(row["case_id"])
            verify_pack(case)
            with zipfile.ZipFile(case.pack_path) as archive:
                assert archive.testzip() is None
                assert "仅供测试" in archive.read("report.html").decode("utf-8")
                assert json.loads(archive.read("manifest.json"))["test_mode"] is True
                receipts.append({"case_id": case.id, "pack": case.pack_path, "verified": True,
                                 "files": archive.namelist(), "approval": case.approval})
    probes = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out.glob("native-pdf-probe*.json"))]
    usage = {k: sum(r["usage"][k] for r in summary) for k in ("requests", "input_tokens", "output_tokens")}
    report = {"rows": summary, "usage": usage, "native_pdf_probes": probes, "packs": receipts,
              "ledger_requests": LiveBudget(out / "live-budget.sqlite3", 36).count(),
              "request_cap": 36, "price_configured": False,
              "scope": "Public examples and deliberately synthetic/invalid cases. No real-client authenticity or end-to-end delivery validation."}
    assert report["ledger_requests"] == usage["requests"] + sum(p["requests"] for p in probes)
    write_json(out / "review.json", report)
    write_json(ROOT / "docs/validation/customer-service.json", report)
    print(json.dumps({"runs": len(summary), "application_pass": sum(r["application_checks"] for r in summary),
                      "semantic_pass": sum(r["semantic_checks"] for r in summary), "usage": usage,
                      "requests_including_probes": report["ledger_requests"], "packs": len(receipts)}))


if __name__ == "__main__":
    summarize()
