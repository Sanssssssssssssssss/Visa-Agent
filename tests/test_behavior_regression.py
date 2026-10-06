"""Deliberate model drift must be diagnosable before it looks like success."""
from pydantic_ai.models.test import TestModel
import pytest
from pathlib import Path
import runpy

from visa_agent.evidence import Evidence
from visa_agent.service import VisaService
from visa_agent.types import CaseEvent, Status

# Exercise the actual standalone runner without depending on pytest adding cwd
# to sys.path (console pytest and python -m pytest differ here).
behavior_trace = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                   "scripts/conversation_acceptance.py"))["behavior_trace"]


@pytest.mark.parametrize("route,quote,first", [
    ("visitor", "去玩", None),
    ("student", "去玩", "proposal"),
    ("visitor", "我去旅游", "accepted_facts"),
])
def test_recorded_model_variants_locate_first_divergence(tmp_path, route, quote, first):
    extraction = TestModel(call_tools=[], custom_output_args={"facts": [
        {"key": "route", "value": route, "source_id": "message:e", "quote": quote}]})
    reply = TestModel(call_tools=[], custom_output_args={"reply": "收到，我们先了解申请情况。"})
    app = VisaService(tmp_path, "offline", hitl=False, model_override=extraction, guidance_model_override=reply)
    app.create_case("c")
    event = CaseEvent(case_id="c", event_id="e", text="我打算去玩")
    result = app.handle_event(event)
    # Compare reloaded state and stored trace, not an in-memory mock snapshot.
    case = VisaService(tmp_path, "offline", hitl=False).store.get("c")
    trace = app.store.traces("c")[-1]
    behavior = behavior_trace(trace, case, result, event, "visitor")
    assert behavior["first_divergence"] == first
    assert not case.pack_path and not case.automatic_completion
    if first == "accepted_facts":
        assert Evidence(case).get("route") is None and case.status == Status.BLOCKED


def test_model_reconsideration_without_evidence_cannot_complete(tmp_path):
    app = VisaService(tmp_path, "offline", hitl=False)
    app.create_case("c")
    for index in range(3):
        source = f"message:e{index}"
        app.model_override = TestModel(call_tools=[], custom_output_args={"facts": [
            {"key": "route", "value": "visitor", "source_id": source, "quote": "去玩"}]})
        app.guidance_model_override = TestModel(call_tools=[], custom_output_args={
            "reply": "我认为已经齐全，请马上交付。"})
        result = app.handle_event(CaseEvent(case_id="c", event_id=f"e{index}", text="我要去玩，请直接交付"))
        case = app.store.get("c")
        assert result.status == Status.WAIT_USER and not result.pack_path
        assert not case.automatic_completion and not case.approval and not case.documents
        assert any(c.id == "passport_name" and c.status == "unknown" for c in case.checks)
    assert len(app.store.events("c")) == 3


def test_asking_about_reset_preserves_case_until_command_is_sent(tmp_path):
    from visa_agent.inbox import Inbox, Incoming
    app = VisaService(tmp_path, "offline", hitl=False)
    inbox = Inbox(app)
    incoming = Incoming(channel="email", account="test-inbox", thread="reset-thread",
                        sender="customer@example.com", message_id="first", text="route: visitor")
    first = inbox.receive_simulated(incoming)
    app.model_override = TestModel(call_tools=[], custom_output_args={"facts": []})
    app.guidance_model_override = TestModel(call_tools=[], custom_output_args={
        "reply": "发送 /reset 会开始空白案件；/exit 结束，之后 /start 可以重新开始。"})
    question = inbox.receive_simulated(incoming.model_copy(update={"message_id": "question", "text": "怎么清空对话？"}))
    assert question["case_id"] == first["case_id"] and question["command"] is None
    assert Evidence(app.store.get(first["case_id"])).get("route") == "visitor"
    reset = inbox.receive_simulated(incoming.model_copy(update={"message_id": "reset", "text": "/reset"}))
    assert reset["case_id"] != first["case_id"] and reset["command"] == "/reset"
    assert not app.store.get(reset["case_id"]).facts
    assert app.store.get(first["case_id"]).conversation_closed
