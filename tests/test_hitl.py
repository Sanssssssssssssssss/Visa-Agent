import json
from pathlib import Path
import zipfile

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.function import FunctionModel

from visa_agent.delivery import manifest, verify_pack
from visa_agent.inbox import Inbox, Incoming
from visa_agent.replay import dataset_path
from visa_agent.service import VisaService
from visa_agent.store import digest
from visa_agent.types import CaseEvent, Status

DATA = Path(__file__).resolve().parents[1] / "datasets"


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("route", ["visitor", "student", "skilled_worker"])
def test_delivery_modes_across_routes(tmp_path, enabled, route):
    service = VisaService(tmp_path, "offline", hitl=enabled)
    service.create_case("case", test_mode=True)
    script = json.loads((DATA / "cases" / f"dev_{route}.json").read_text(encoding="utf-8"))
    for i, item in enumerate(script["events"]):
        if not enabled and i == len(script["events"]) - 1:
            def unavailable(messages, info):
                raise RuntimeError("A completed collection must not need another model decision")
            service.guidance_model_override = FunctionModel(unavailable)
        result = service.handle_event(CaseEvent(case_id="case", event_id=str(i), text=item["text"],
                    attachments=[str(dataset_path(DATA, p)) for p in item["attachments"]]))
        assert not result.error
    case = service.store.get("case")
    assert case.status == (Status.READY if enabled else Status.COMPLETE)
    assert case.approval is None
    verify_pack(case)
    if not enabled:
        assert case.automatic_completion.basis == "checklist"
        assert service.store.traces(case.id)[-1]["reply_error"] == "RuntimeError"
        assert result.reply and result.pack_path
        assert case.automatic_completion.manifest_hash == digest(manifest(case))
        assert case.automatic_completion.version == case.version
        with zipfile.ZipFile(case.pack_path) as archive:
            review = json.loads(archive.read("review.json"))
            assert review["approval"] is None and review["automatic_completion"]
            assert "未经人工审核" in archive.read("report.html").decode()
        with pytest.raises(ValueError, match="disabled"):
            service.review_case(case.id, case.version, "approve", "Cannot invent human approval")
        updated = service.handle_event(CaseEvent(case_id="case", event_id="changed", text="applicant_name: Another Name"))
        assert updated.status == Status.BLOCKED and not service.store.get(case.id).automatic_completion
        assert not service.store.get(case.id).pack_path


def test_pack_write_failure_cannot_send_collection_complete(tmp_path, monkeypatch):
    service = VisaService(tmp_path, "offline", hitl=False)
    service.create_case("case", test_mode=True)
    script = json.loads((DATA / "cases/dev_visitor.json").read_text(encoding="utf-8"))
    def disk_error(*args):
        raise OSError("Test disk failure")
    monkeypatch.setattr("visa_agent.service.build_pack", disk_error)
    for i, item in enumerate(script["events"]):
        result = service.handle_event(CaseEvent(case_id="case", event_id=str(i), text=item["text"],
            attachments=[str(dataset_path(DATA, p)) for p in item["attachments"]]))
    assert result.error and result.status == Status.BLOCKED
    assert not service.store.get("case").automatic_completion and not result.pack_path
    assert "Document collection complete!" not in result.reply and "材料收集完成！" not in result.reply


def test_disabled_hitl_still_rejects_model_attempt_to_deliver_missing_evidence(tmp_path):
    bad = TestModel(call_tools=[], custom_output_args={"actions": ["route"], "delivery_decision": "deliver"})
    service = VisaService(tmp_path, "offline", hitl=False, guidance_model_override=bad)
    service.create_case("case")
    result = service.handle_event(CaseEvent(case_id="case", event_id="e", text="age: 30"))
    assert result.status == Status.WAIT_USER and not result.pack_path
    assert service.store.traces("case")[-1]["reply_error"]
    assert service.store.get("case").automatic_completion is None


def test_policy_is_operator_owned_and_bound_to_case_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("VISA_HITL", "off")
    service = VisaService(tmp_path, "offline")
    inbox = Inbox(service)
    incoming = Incoming(channel="email", account="a", sender="lin@example.com", thread="t", message_id="1", text="/start")
    first = inbox.receive_simulated(incoming)
    assert not service.store.get(first["case_id"]).hitl_enabled
    restarted = Inbox(VisaService(tmp_path, "offline", hitl="on"))
    assert not restarted.store.get(first["case_id"]).hitl_enabled
    reset = restarted.receive_simulated(incoming.model_copy(update={"message_id": "2", "text": "/reset"}))
    assert restarted.store.get(reset["case_id"]).hitl_enabled
    with pytest.raises(ValueError):
        Incoming.model_validate({**incoming.model_dump(), "hitl_enabled": False})
    monkeypatch.setenv("VISA_HITL", "typo")
    with pytest.raises(ValueError, match="on or off"):
        VisaService(tmp_path, "offline")
