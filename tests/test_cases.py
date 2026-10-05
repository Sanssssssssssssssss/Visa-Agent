from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from visa_agent.replay import replay, verify_dataset
from visa_agent.service import VisaService
from visa_agent.types import CaseEvent, Status

DATASET = Path(__file__).resolve().parents[1] / "datasets"
CASES = ["visitor", "student", "skilled_worker", "ambiguous_route", "missing_document",
         "unreadable_image", "name_conflict", "funds_period", "missing_translation",
         "duplicate_event", "restart", "stale_approval"]


@pytest.mark.parametrize("name", CASES)
def test_development_scenario(name, tmp_path):
    report = replay(VisaService(tmp_path, "offline"), DATASET / "cases" / f"dev_{name}.json", approve_demo=True)
    assert report["passed"], {"results": report["results"],
                              "failures": [a for a in report["assertions"] if not a["passed"]]}
    if report["pack_path"]:
        with zipfile.ZipFile(report["pack_path"]) as archive:
            assert archive.testzip() is None
            manifest = json.loads(archive.read("manifest.json"))
            assert all(c["status"] in {"pass", "not_applicable"} for c in manifest["checks"])
            assert "report.html" in archive.namelist()


def test_event_key_cannot_change_payload(tmp_path):
    service = VisaService(tmp_path, "offline")
    service.store.create("case")
    service.handle_event(CaseEvent(case_id="case", event_id="e1", text="age: 30"))
    with pytest.raises(ValueError, match="different content"):
        service.handle_event(CaseEvent(case_id="case", event_id="e1", text="age: 40"))


def test_reminders_do_not_call_model_and_stop_after_two(tmp_path):
    service = VisaService(tmp_path, "offline")
    case = service.store.create("case")
    start = datetime.now(timezone.utc)
    results = []
    for i in (1, 2, 3):
        results.append(service.handle_event(CaseEvent(case_id=case.id, event_id=f"tick{i}", kind="tick",
                                                      at=start + timedelta(days=i))))
    final = service.store.get(case.id)
    assert final.reminder_count == 2
    assert final.status == Status.WAIT_USER
    assert "顾问跟进" in results[-1].reply
    assert not any("usage" in t for t in service.store.traces(case.id))


def test_process_restart_through_cli(tmp_path):
    def cli(*args):
        result = subprocess.run([sys.executable, "-m", "visa_agent.cli", "--data", str(tmp_path),
                                 "--mode", "offline", *args], capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    cli("new", "restarted")
    sent = cli("message", "restarted", "age: 30", "--event-id", "one")
    inspected = cli("inspect", "restarted")
    assert inspected["version"] == sent["version"]
    assert inspected["facts"][0]["value"] == "30"
    assert cli("message", "restarted", "age: 30", "--event-id", "one")["duplicate"]


def test_frozen_dataset():
    assert len(verify_dataset(DATASET)) == 64


def test_review_pack_tampering_is_rejected(tmp_path):
    service = VisaService(tmp_path, "offline")
    report = replay(service, DATASET / "cases" / "dev_visitor.json")
    case = service.store.get(report["case_id"])
    with zipfile.ZipFile(case.pack_path, "w") as archive:
        archive.writestr("manifest.json", '{}')
    with pytest.raises(ValueError, match="manifest was modified"):
        service.review_case(case.id, case.version, "approve", "Test altered pack")
    assert service.store.get(case.id).approval is None


def test_rule_change_invalidates_complete_on_next_event(tmp_path, monkeypatch):
    service = VisaService(tmp_path, "offline")
    report = replay(service, DATASET / "cases" / "dev_visitor.json", approve_demo=True)
    monkeypatch.setattr("visa_agent.service.RULE_VERSION", "new-rule-version")
    case = service.store.get(report["case_id"])
    result = service.handle_event(CaseEvent(case_id=case.id, event_id="new_tick", kind="tick"))
    assert result.status == Status.NEEDS_HUMAN
    assert service.store.get(case.id).approval is None
