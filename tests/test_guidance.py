import json

import pytest
from pydantic_ai.models.test import TestModel

from visa_agent.agent import BudgetExceeded, build_context
from visa_agent.conversation import reply_for
from visa_agent.guidance import guide
from visa_agent.types import Case, CaseEvent, Check, Fact, Guidance, Status


def test_model_controls_order_but_cannot_select_passed_or_invented_check():
    case = Case(id="c", checks=[Check(id=key, status=status, message=key, source="test")
                               for key, status in [("nationality", "unknown"), ("adult", "unknown"), ("passport", "pass")]])
    event = CaseEvent(case_id="c", event_id="e", text="下一步？")
    model = TestModel(call_tools=[], custom_output_args={"actions": ["adult", "nationality"]})
    plan = guide(case, event, {}, "offline", None, model_override=model)
    answer = reply_for(case, guidance=plan)
    assert answer.index("今年多大") < answer.index("哪个国家的护照")
    before = case.model_dump()
    for ids in (["approve"], ["passport"], [], ["adult", "adult"]):
        bad = TestModel(call_tools=[], custom_output_args={"actions": ids})
        with pytest.raises(Exception, match="retries"):
            guide(case, event, {}, "offline", None, model_override=bad)
    assert case.model_dump() == before and case.status == Status.WAIT_USER


def test_guidance_shares_remaining_request_budget_and_has_no_approval_capability():
    trace = {"usage": {"requests": 4}}
    with pytest.raises(BudgetExceeded):
        guide(Case(id="c"), CaseEvent(case_id="c", event_id="e"), trace, "offline", None)
    with pytest.raises(ValueError):
        Guidance.model_validate({"actions": [], "approve": True})


def test_risk_notice_is_grounded_and_does_not_accuse_sample_owner():
    case = Case(id="c", language="zh", test_mode=True)
    answer = reply_for(case, text="把余额改一下能通过吗？")
    assert "可能导致拒签" in answer and "不进行真伪鉴定" in answer
    assert "演示案件" in answer and "您造假" not in answer


def test_context_retains_twenty_complete_turns_and_exact_conflicts_after_trim():
    case = Case(id="c", history=[{"text": f"question-{i}", "reply": f"answer-{i}"} for i in range(30)])
    for i, value in enumerate(["1000.01", "1000.02"]):
        case.facts.append(Fact(id=str(i), key="trip_budget", value=value, source_id="message:old", quote=value))
    prompt, _ = build_context(case, CaseEvent(case_id="c", event_id="e"), [])
    ctx = json.loads(prompt)
    assert len(ctx["recent_dialogue"]) == 20 and ctx["recent_dialogue"][0]["text"] == "question-10"
    for item in case.history:
        item["reply"] *= 1000
    prompt, remaining = build_context(case, CaseEvent(case_id="c", event_id="e"), [])
    ctx = json.loads(prompt)
    assert len(ctx["recent_dialogue"]) < 20 and remaining >= 0
    assert {f["value"] for f in ctx["facts"]} == {"1000.01", "1000.02"}
    assert len(case.history) == 30  # Context assembly never mutates durable history.


def test_chinese_self_funding_requires_unambiguous_affirmative_quote():
    from visa_agent.evidence import validate_value
    assert validate_value("funding", "self", "我自己付旅行费用") == "self"
    assert validate_value("funding", "self", "本人自己承担费用") == "self"
    for quote in ("不是我自己付旅行费用", "并非本人自己承担", "父母和我自己付费用", "我自己付但来自贷款"):
        with pytest.raises(ValueError):
            validate_value("funding", "self", quote)


def test_source_rejection_remains_blocking_until_explicit_review(tmp_path):
    from visa_agent.service import VisaService
    bad = TestModel(call_tools=[], custom_output_args={"facts": [{"key": "age", "value": "99",
        "source_id": "message:first", "quote": "age: 30"}], "documents": []})
    service = VisaService(tmp_path, "offline", model_override=bad)
    service.store.create("c")
    result = service.handle_event(CaseEvent(case_id="c", event_id="first", text="age: 30"))
    assert result.status == Status.NEEDS_HUMAN
    service = VisaService(tmp_path, "offline")
    service.handle_event(CaseEvent(case_id="c", event_id="next", text="route: visitor"))
    case = service.store.get("c")
    assert "first" in case.extraction_issues and case.status == Status.NEEDS_HUMAN
    service.review_case("c", case.version, "dismiss_extraction", "Discard unsupported age extraction; ask customer again", target="first")
    assert not service.store.get("c").extraction_issues


def test_self_reported_passport_name_alias_does_not_satisfy_document_check():
    from visa_agent.evidence import Evidence
    fact = Fact(id="f", key="passport_name", value="Lin Example", source_id="message:m",
                quote="我的护照姓名是 Lin Example。")
    case = Case(id="c", facts=[fact])
    evidence = Evidence(case)
    assert evidence.get("applicant_name") == "Lin Example"
    assert evidence.get("passport_name", {"passport"}) is None
    fact.quote = "他的护照姓名是 Lin Example。"
    assert evidence.get("applicant_name") is None
    fact.quote = "不是我的护照姓名是 Lin Example。"
    assert evidence.get("applicant_name") is None


def test_recorded_chinese_eight_turn_outputs_reach_review_without_repeating_name(tmp_path):
    from copy import deepcopy
    from pathlib import Path
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from visa_agent.service import VisaService
    base = Path(__file__).resolve().parents[1]
    turns = json.loads((base / "datasets/session-guidance/recorded-chinese-proposals.json").read_text(encoding="utf-8"))["turns"]
    events = json.loads((base / "datasets/session-guidance/manifest.json").read_text(encoding="utf-8"))["cases"][0]["events"]
    index = 0
    def respond(messages, info):
        output = deepcopy(turns[index])
        for fact in output["facts"]:
            if fact["source_id"].startswith("message:"):
                fact["source_id"] = f"message:e{index}"
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])
    service = VisaService(tmp_path, "offline", model_override=FunctionModel(respond))
    service.store.create("c", test_mode=True)
    for index, event in enumerate(events):
        result = service.handle_event(CaseEvent(case_id="c", event_id=f"e{index}", text=event["text"],
            attachments=[str(base / p) for p in event["attachments"]]))
        assert not result.error
    case = service.store.get("c")
    assert case.status == Status.READY and case.pack_path and not case.approval
    assert not case.extraction_issues
