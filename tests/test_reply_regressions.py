"""Public-scan failures: account headings, slash dates and repetitive replies."""

import pytest

from visa_agent.evidence import apply_proposal, validate_value
from visa_agent.rules import reply_for
from visa_agent.types import Candidate, Case, Check, Document, Page, Proposal, Status


def test_account_heading_is_not_a_holder_even_when_quote_is_exact():
    text = "ESAVINGS ACCOUNT\nCURRENT ACCOUNT\nAccount holder: Alex Bank"
    doc = Document(id="doc", name="statement.png", sha256="a" * 64, path="unused",
                   pages=[Page(number=1, text=text, method="ocr")])
    case = Case(id="unit", documents=[doc])
    candidates = [Candidate(key="bank_holder", value=value, quote=value, page=1,
                            source_id="doc", confidence="low")
                  for value in ("ESAVINGS ACCOUNT", "CURRENT ACCOUNT", "Alex Bank")]
    rejected = apply_proposal(case, Proposal(facts=candidates), {})
    assert len(rejected) == 2
    assert [fact.value for fact in case.facts] == ["Alex Bank"]


def test_year_first_slash_dates_are_grounded_and_canonical():
    assert validate_value("bank_start", "2014/05/21", "2014/05/21") == "2014-05-21"
    for value, quote in [("05/06/2014", "05/06/2014"), ("2014/02/31", "2014/02/31"),
                         ("2014/05/21", "2014/05/22")]:
        with pytest.raises(ValueError):
            validate_value("bank_start", value, quote)


def test_three_image_upload_gets_one_pagination_action():
    docs = [Document(id=f"d{i}", name=f"page{i}.png", path="unused", sha256=str(i) * 64,
                     problems=["Declared pagination incomplete: missing pages"])
            for i in range(1, 4)]
    checks = [Check(id="applicant_name", status="unknown", source="test", message="请提供姓名。")]
    for doc in docs:
        checks += [Check(id="read:" + doc.id, status="fail", source="test", message="请重传。"),
                   Check(id="pagination:" + doc.id, status="unknown", human=True,
                         source="test", message="每张图片又问一次页码。")]
    case = Case(id="unit", status=Status.NEEDS_HUMAN, documents=docs, checks=checks)
    reply = reply_for(case)
    assert "已收到 3 个文件" in reply and reply.count("合并为 PDF") == 1
    assert "请提供姓名" in reply and "请重传" not in reply
    assert "缺少" not in reply  # Consecutive separate images do not prove a missing page.
    assert reply.count("\n1.") == 1 and "\n4." not in reply


def test_uploaded_document_problem_precedes_routine_intake_questions():
    doc = Document(id="d", name="certificate.png", path="unused", sha256="a" * 64,
                   problems=["page 1: low OCR confidence"])
    checks = [Check(id=k, status="unknown", source="test", message="背景问题：" + k)
              for k in ("applicant_name", "nationality", "age")]
    checks.append(Check(id="read:d", status="fail", source="test", message="读取失败"))
    reply = reply_for(Case(id="unit", documents=[doc], checks=checks))
    assert reply.splitlines()[2].startswith("1. certificate.png")
    assert "无法可靠读取" in reply and "\n4." not in reply
