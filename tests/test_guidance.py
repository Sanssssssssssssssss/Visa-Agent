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


def test_explicit_chinese_dates_from_live_mail_are_grounded():
    from visa_agent.evidence import validate_value
    for quote in ("预计2026年12月10日去英国旅游", "2026年12月10号", "2026 年 12 月 10 日"):
        assert validate_value("travel_start", "2026-12-10", quote) == "2026-12-10"
    assert validate_value("travel_start", "2026-02-01", "2026年02月01日") == "2026-02-01"


def test_date_guard_does_not_invent_year_or_accept_mismatched_chinese_date():
    from visa_agent.evidence import validate_value
    for quote in ("12月17日回来", "2026年12月10日出发，12月17日回来", "2027年12月17日", "2026年11月17日"):
        with pytest.raises(ValueError, match="not grounded"):
            validate_value("travel_end", "2026-12-17", quote)


def test_model_invented_year_in_initial_customer_date_is_logged_and_asked_not_saved(tmp_path):
    from visa_agent.service import VisaService
    from visa_agent.evidence import Evidence
    model = TestModel(call_tools=[], custom_output_args={"facts": [
        {"key": "travel_start", "value": "2026-12-10", "source_id": "message:first", "quote": "2026年12月10日"},
        {"key": "travel_end", "value": "2026-12-17", "source_id": "message:first", "quote": "12月17日回来"},
    ]})
    app = VisaService(tmp_path, "offline", hitl=False, model_override=model)
    app.create_case("c")
    result = app.handle_event(CaseEvent(case_id="c", event_id="first", text="2026年12月10日出发，12月17日回来"))
    case = app.store.get("c")
    assert result.status == Status.WAIT_USER and not case.extraction_issues
    assert Evidence(case).get("travel_start") == "2026-12-10"
    assert Evidence(case).get("travel_end") is None
    trace = app.store.traces("c")[-1]
    assert trace["unconfirmed_candidates"][0]["reason"] == "date_year_missing"
    assert any(d["code"] == "date_year_missing" for d in trace["diagnostics"])


def test_partial_date_exception_cannot_bypass_documents_mismatch_or_existing_date():
    from visa_agent.evidence import apply_proposal
    from visa_agent.types import Candidate, Document, Page, Proposal
    for source, value, previous in [("file", "2026-12-17", False),
                                    ("message:m", "2026-12-18", False),
                                    ("message:m", "2026-12-17", True)]:
        case = Case(id="c", documents=[Document(id="file", path="unused", name="bank.pdf", sha256="a"*64,
                                               pages=[Page(number=1, text="12月17日", method="pdf_text")])])
        if previous:
            case.facts.append(Fact(id="old", key="travel_end", value="2026-12-20",
                                   source_id="message:old", quote="2026-12-20"))
        proposal = Proposal(facts=[Candidate(key="travel_end", value=value, source_id=source,
                                             page=1 if source == "file" else None, quote="12月17日")])
        pending = []
        assert apply_proposal(case, proposal, {"message:m": "12月17日"}, unconfirmed=pending)
        assert not pending and len(case.facts) == (1 if previous else 0)


def test_initial_application_location_guessed_from_residence_remains_a_question(tmp_path):
    from visa_agent.service import VisaService
    from visa_agent.evidence import Evidence
    model = TestModel(call_tools=[], custom_output_args={"facts": [
        {"key": "residence_country", "value": "China", "source_id": "message:first", "quote": "住在中国"},
        {"key": "application_location", "value": "outside_uk", "source_id": "message:first", "quote": "住在中国"},
    ]})
    app = VisaService(tmp_path, "offline", hitl=False, model_override=model)
    app.create_case("c")
    result = app.handle_event(CaseEvent(case_id="c", event_id="first", text="我住在中国，怎么准备签证？"))
    case = app.store.get("c")
    assert result.status == Status.WAIT_USER and not case.extraction_issues
    assert Evidence(case).get("residence_country") == "China"
    assert Evidence(case).get("application_location") is None
    assert any(c.id == "application_location" and c.status == "unknown" for c in case.checks)
    trace = app.store.traces("c")[-1]
    assert any(d["next_action"] == "confirm_application_location" for d in trace["diagnostics"])


def test_location_question_exception_cannot_override_previous_answer_or_document():
    from visa_agent.evidence import apply_proposal
    from visa_agent.types import Candidate, Document, Page, Proposal
    for source in ("message:m", "file"):
        case = Case(id="c", documents=[Document(id="file", path="unused", name="doc.pdf", sha256="a"*64,
                                               pages=[Page(number=1, text="住在中国", method="pdf_text")])])
        if source.startswith("message:"):
            case.facts.append(Fact(id="old", key="application_location", value="inside_uk",
                                   source_id="message:old", quote="英国境内"))
        proposal = Proposal(facts=[Candidate(key="application_location", value="outside_uk", source_id=source,
                                             page=1 if source == "file" else None, quote="住在中国")])
        pending = []
        assert apply_proposal(case, proposal, {"message:m": "住在中国"}, unconfirmed=pending)
        assert not pending and not any(f.value == "outside_uk" for f in case.facts)


@pytest.mark.parametrize("language", ["zh", "en"])
def test_sample_disclosure_survives_model_choosing_only_intake_questions(language):
    from visa_agent.types import Document
    case = Case(id="live-mail", language=language, hitl_enabled=False,
                documents=[Document(id="d", path="unused", name="identity.pdf", sha256="a"*64,
                                    kind="passport", content_role="sample")],
                checks=[Check(id=key, status=status, message="test", source="test") for key, status in
                        [("sample:d", "fail"), ("travel_start", "unknown"), ("funding", "unknown")]])
    plan = Guidance(actions=["travel_start", "funding"])
    answer = reply_for(case, received_count=1, guidance=plan)
    assert "identity.pdf" in answer
    assert ("不能作为您本人的正式申请证据" if language == "zh" else "cannot count as your application evidence") in answer
    assert "1. " in answer and "2. " in answer and "3. " not in answer


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
