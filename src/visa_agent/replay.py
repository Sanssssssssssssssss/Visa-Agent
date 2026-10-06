"""Frozen, scripted customer inputs. Expected answers never enter the agent context."""

import hashlib
import json
from pathlib import Path
import uuid

from .evidence import Evidence
from .service import VisaService
from .store import write_json
from .types import CaseEvent, Status, now_utc


def dataset_path(root: Path, name: str) -> Path:
    # Frozen Windows fixtures keep their original bytes; interpret separators portably.
    path = (root / name.replace("\\", "/")).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Dataset path escapes dataset directory")
    return path


def verify_dataset(root: Path) -> str:
    frozen = root / "freeze.json"
    manifest = json.loads(frozen.read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        path = dataset_path(root, name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen dataset changed: {name}")
    return hashlib.sha256(frozen.read_bytes()).hexdigest()


def replay(service: VisaService, scenario_path: Path, *, approve_demo=False) -> dict:
    if not service.hitl_enabled:
        raise ValueError("Frozen replay expectations require --hitl on; use scripts/hitl_acceptance.py to test both modes")
    root = scenario_path.resolve().parent.parent
    frozen_hash = verify_dataset(root)
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    case_id = scenario["id"] + "-" + uuid.uuid4().hex[:8]
    service.create_case(case_id, test_mode=True)  # This command consumes the frozen synthetic dataset.
    results, assertions = [], []
    event_states, before_adviser = [], None
    for index, item in enumerate(scenario["events"]):
        if index >= 8:
            raise ValueError("Scenario exceeds eight customer turns")
        files = [dataset_path(root, p) for p in item.get("attachments", [])]
        event = CaseEvent(case_id=case_id, event_id=f"event_{index}", text=item["text"],
                          attachments=[str(p) for p in files], kind="upload" if files else "message")
        result = service.handle_event(event)
        results.append(result.model_dump())
        if result.error:
            break
        if action := item.get("adviser_after"):
            case = service.store.get(case_id)
            before_adviser = case.status
            doc = next(d for d in case.documents if d.name == action["document_name"] and not d.rejected)
            case = service.review_case(case.id, case.version, action["decision"], action["notes"],
                                       reviewer="synthetic-test-adviser", target=doc.id)
            event_states.append(case.status)
        else:
            event_states.append(result.status)
        if scenario["exercise"] == "duplicate_event":
            duplicate = service.handle_event(event)
            assertions.append({"name": "duplicate_event", "passed": duplicate.duplicate and duplicate.version == result.version})
        if scenario["exercise"] == "restart":
            service = VisaService(service.store.root, service.mode, budget=service.budget)
    case = service.store.get(case_id)
    # Read expected answers ONLY after execution. The model tools cannot access these files.
    expected = json.loads((root / "expected" / scenario_path.name).read_text(encoding="utf-8"))
    assertions.append({"name": "event_states", "passed": event_states == expected["event_states"],
                       "expected": expected["event_states"], "actual": event_states})
    if "before_adviser_state" in expected:
        assertions.append({"name": "conflict_before_review", "passed": before_adviser == expected["before_adviser_state"]})
    assertions.append({"name": "status", "passed": case.status == expected["expected_status"],
                       "expected": expected["expected_status"], "actual": case.status})
    blockers = [c.id for c in case.checks if c.status in {"fail", "unknown"}]
    for key in expected["expected_blockers"]:
        assertions.append({"name": f"blocker:{key}", "passed": key in blockers})
    evidence = Evidence(case)
    for key, value in expected["expected_fields"].items():
        actual = evidence.get(key)
        assertions.append({"name": f"field:{key}", "passed": actual == value,
                           "expected": value, "actual": actual})
        if source := expected.get("expected_sources", {}).get(key):
            source_id = (hashlib.sha256(dataset_path(root, source["attachment"]).read_bytes()).hexdigest()[:20]
                         if "attachment" in source else "message:" + source["event_id"])
            assertions.append({"name": f"source:{key}", "passed": any(
                f.source_id == source_id and f.page == source["page"] and f.value == value for f in evidence.facts(key))})
    if scenario["exercise"] == "duplicate_event" and scenario["events"][-1]["attachments"]:
        version, count = case.version, len(case.documents)
        duplicate_files = CaseEvent(case_id=case.id, event_id="redelivered_files", kind="upload",
                                    attachments=[str(dataset_path(root, p)) for p in scenario["events"][-1]["attachments"]])
        result = service.handle_event(duplicate_files)
        case = service.store.get(case.id)
        assertions.append({"name": "duplicate_files", "passed": case.version == version and len(case.documents) == count and not result.error})
    approved = False
    if approve_demo and case.status == Status.READY:
        case = service.review_case(case.id, case.version, "approve",
                                   "Scripted adviser action on synthetic fixtures; not a real professional review.",
                                   reviewer="synthetic-test-adviser")
        approved = True
        assertions.append({"name": "review_and_pack", "passed": case.status == Status.COMPLETE and Path(case.pack_path).is_file()})
    if scenario["exercise"] == "stale_approval" and case.status in {Status.READY, Status.COMPLETE}:
        old_version = case.version
        if case.status == Status.READY:
            case = service.review_case(case.id, case.version, "approve", "Synthetic version-invalidating test",
                                       reviewer="synthetic-test-adviser")
        service.handle_event(CaseEvent(case_id=case.id, event_id="changed_budget", text="trip_budget: 4000"))
        blocked = False
        try:
            service.review_case(case.id, old_version, "approve", "Must reject stale approval")
        except ValueError:
            blocked = True
        case = service.store.get(case.id)
        assertions.append({"name": "stale_approval", "passed": blocked and case.approval is None and case.status != Status.COMPLETE})
    traces = service.store.traces(case_id)
    usage = {key: sum(t.get("usage", {}).get(key, 0) for t in traces)
             for key in ("input_tokens", "output_tokens", "requests")}
    return {"scenario": scenario["id"], "case_id": case_id, "mode": service.mode,
            "at": now_utc(), "dataset_hash": frozen_hash, "rule_version": case.rule_version,
            "passed": all(a["passed"] for a in assertions) and not any(r["error"] for r in results),
            "scripted_review": approved, "final_status": case.status, "results": results,
            "assertions": assertions, "usage": usage, "http_requests": sum(t.get("http_requests",0) for t in traces),
            "pack_path": case.pack_path, "trace_ids": [t["run_id"] for t in traces]}


def run_suite(service, dataset: Path, output: Path, *, live=False, only=None):
    verify_dataset(dataset)
    ids = only or (["dev_visitor", "dev_student", "dev_skilled_worker", "holdout_visitor",
                    "holdout_student", "holdout_skilled_worker"] if live else
                   [p.stem for p in sorted((dataset / "cases").glob("dev_*.json"))])
    reports = []
    for id in ids:
        print(f"Running {id} ({service.mode})", flush=True)
        report = replay(service, dataset / "cases" / f"{id}.json", approve_demo=True)
        reports.append(report)
        write_json(output / f"{id}.json", report)
        failures = [a["name"] for a in report["assertions"] if not a["passed"]]
        print(f"  {'PASS' if report['passed'] else 'FAIL'} {report['final_status']} {failures[:8]}", flush=True)
        # Budget exhaustion stops the suite without inventing results for the remainder.
        if any(r["error"] and "budget" in r["error"].lower() for r in report["results"]):
            break
    summary = {"mode": service.mode, "at": now_utc(), "requested": ids,
               "completed": len(reports), "passed": sum(r["passed"] for r in reports),
               "reports": reports, "live_budget_used": service.budget.count()}
    write_json(output / "summary.json", summary)
    return summary
