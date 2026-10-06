"""Received bank evidence must not be confused with missing course information."""
from decimal import Decimal

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, ToolCallPart

from visa_agent.conversation import material_progress, progress_text
from visa_agent.evidence import Evidence
from visa_agent.guidance import guide
from visa_agent.rules import _finance
from visa_agent.types import Case, CaseEvent, Check, Document, Fact, Page, Route


def bank_case(**updates):
    fields = {"bank_name": "Example Bank", "bank_holder": "Mei Example", "bank_currency": "GBP",
              "bank_minimum": "40000", "bank_start": "2026-08-01", "bank_end": "2026-09-28"}
    fields.update(updates)
    case = Case(id="c", route=Route.STUDENT,
                documents=[Document(id="bank", name="funds-scan.pdf", path="unused", sha256="a"*64,
                                    kind="bank_statement", content_role="evidence", language="en")])
    for key, value in fields.items():
        case.facts.append(Fact(id=key, key=key, value=value, source_id="bank", page=1, quote=value))
    case.facts.append(Fact(id="date", key="application_date", value="2026-10-05",
                           source_id="message:old", quote="2026-10-05"))
    return case


def test_cas_dependency_is_unknown_with_readable_bank_evidence():
    case = bank_case()
    _finance(Evidence(case), case.checks, None, period=True, source="student_money")
    checks = {c.id: c for c in case.checks}
    assert checks["finance_document"].status == "pass"
    assert checks["finance"].status == "unknown" and checks["finance"].evidence
    assert "CAS" in checks["finance"].message and "无需" in checks["finance"].message
    trace = {}
    guide(case, CaseEvent(case_id="c", event_id="e", text="我的资金证明呢？"), trace, "offline", None,
          model_override=TestModel(call_tools=[], custom_output_args={"reply": "资金证明收到了，等 CAS 核对金额。"}))
    assert trace["guidance_context"]["allowed_actions"]["finance"] == checks["finance"].message
    assert trace["guidance_context"]["progress"]["received"] == 1


@pytest.mark.parametrize("updates,required", [({"bank_end": "2026-08-10"}, None),
                                             ({"bank_minimum": "100"}, Decimal("26539"))])
def test_bad_financial_evidence_still_fails(updates, required):
    case = bank_case(**updates)
    _finance(Evidence(case), case.checks, required, period=True, source="student_money")
    assert next(c for c in case.checks if c.id == "finance").status == "fail"


def test_course_information_unlocks_existing_bank_file_without_reupload():
    case = bank_case()
    _finance(Evidence(case), case.checks, None, period=True, source="student_money")
    source_ids = {f.source_id for f in case.facts if f.key.startswith("bank_")}
    case.checks = []
    _finance(Evidence(case), case.checks, Decimal("26539"), period=True, source="student_money")
    assert next(c for c in case.checks if c.id == "finance").status == "pass"
    assert len(case.documents) == 1 and source_ids == {"bank"}


def test_receipt_counts_three_files_while_two_categories_are_checked():
    case = bank_case()
    case.documents.extend(Document(id=kind, name=name, path="unused", sha256=kind,
                                   kind=kind, content_role="evidence")
                          for kind, name in [("passport", "identity.jpg"), ("tb", "health.jpg")])
    for key in ("passport_name", "passport_number", "passport_valid", "tb_name", "tb_valid"):
        case.checks.append(Check(id=key, status="pass", message="checked", source="test"))
    case.checks.append(Check(id="cas_reference", status="unknown", message="CAS missing", source="test"))
    _finance(Evidence(case), case.checks, None, period=True, source="student_money")
    progress = material_progress(case)
    assert (progress["received"], progress["checked"], progress["total"]) == (3, 2, 4)
    funds = next(item for item in progress["items"] if item["id"] == "funds")
    assert funds["status"] == "received" and funds["files"] == ["funds-scan.pdf"]
    footer = progress_text(case)
    assert "已收到 3/4" in footer and "已核对 2/4" in footer


@pytest.mark.parametrize("recover", [True, False])
def test_bank_field_recheck_is_bounded_and_does_not_force_invention(recover):
    from visa_agent.agent import ReadContext, make_agent
    fields = {"bank_name": "Example Bank", "bank_holder": "Mei Example", "bank_currency": "GBP",
              "bank_minimum": "40000", "bank_start": "2026-08-01", "bank_end": "2026-09-28"}
    text = "\n".join(fields.values()) if recover else "\n".join(v for k, v in fields.items() if k != "bank_name")
    doc = Document(id="bank", name="bank.pdf", path="unused", sha256="a"*64, kind="bank_statement",
                   content_role="evidence", pages=[Page(number=1, text=text, method="pdf_text")])
    calls = []
    def respond(messages, info):
        calls.append(1)
        facts = [{"key": k, "value": v, "source_id": "bank", "page": 1, "quote": text}
                 for k, v in fields.items() if k != "bank_name" or (recover and len(calls) > 1)]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"facts": facts})])
    trace = {}
    result = make_agent(FunctionModel(respond)).run_sync("Read the bank fields", deps=ReadContext({"bank": doc}, trace, 5000))
    assert len(calls) == 2 and result.usage.requests == 2
    assert trace["bank_extraction_recheck"]["missing_before"] == {"bank": ["bank_name"]}
    assert trace["bank_extraction_recheck"]["remaining_after"] == ({} if recover else {"bank": ["bank_name"]})
    assert any(f.key == "bank_name" for f in result.output.facts) == recover


def test_incomplete_bank_lists_the_specific_unconfirmed_field():
    case = bank_case()
    case.facts = [f for f in case.facts if f.key != "bank_name"]
    _finance(Evidence(case), case.checks, None, period=True, source="student_money")
    finance = next(c for c in case.checks if c.id == "finance")
    assert "银行名称" in finance.message and "持有人" not in finance.message
