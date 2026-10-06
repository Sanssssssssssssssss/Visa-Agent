"""Real failures from the frozen adversarial batch, tested without model access."""

from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from visa_agent.agent import extract
from visa_agent.documents import read_document
from visa_agent.evidence import apply_proposal, validate_value
from visa_agent.types import Candidate, Case, CaseEvent, Document, Page, Proposal

MATERIALS = Path(__file__).resolve().parents[1] / "datasets/bad-cases/materials"


def test_visual_redaction_never_exposes_concealed_name():
    path = MATERIALS / "concealed-holder.pdf"
    doc = read_document(path, "a" * 64, path.name)
    assert doc.pages[0].method == "ocr"
    assert "Alex River" not in doc.pages[0].text
    assert "35000" in doc.pages[0].text


def test_declared_missing_page_is_a_document_problem():
    path = MATERIALS / "missing-page.pdf"
    doc = read_document(path, "b" * 64, path.name)
    assert doc.pages and any("missing" in problem.lower() for problem in doc.problems)


def test_numeric_boolean_needs_corresponding_negative_evidence():
    assert validate_value("dependants", "0", "I have no dependants") == "false"
    with pytest.raises(ValueError):
        validate_value("dependants", "0", "I do have dependants")


def test_natural_country_and_funding_are_canonical_but_ambiguity_is_rejected():
    assert validate_value("nationality", "Indian", "I am an Indian national") == "India"
    assert validate_value("funding", "I am paying using my own money.",
                          "I am paying using my own money.") == "self"
    for quote in ("I am not self-funded", "I use my own money and my employer pays",
                  "My own money comes from a loan"):
        with pytest.raises(ValueError):
            validate_value("funding", "self", quote)


def test_signatory_and_company_cannot_become_applicant_names():
    text = "Employer: River Studio Ltd.\nYours sincerely,\nG HUGHES\nDIRECTOR OF STUDENT LIFE"
    doc = Document(id="doc", name="letter.pdf", path="unused", sha256="d"*64,
                   pages=[Page(number=1, text=text, method="pdf_text")])
    case = Case(id="unit", documents=[doc])
    candidates = [Candidate(key="cas_name", value="G HUGHES", source_id="doc", page=1,
                            quote="G HUGHES"),
                  Candidate(key="employment_name", value="River Studio Ltd", source_id="doc", page=1,
                            quote="Employer: River Studio Ltd."),
                  Candidate(key="employer", value="River Studio Ltd", source_id="doc", page=1,
                            quote="Employer: River Studio Ltd.")]
    errors = apply_proposal(case, Proposal(facts=candidates), {})
    assert len(errors) == 2
    assert [f.key for f in case.facts] == ["employer"]


def test_university_name_cannot_become_cas_student_name():
    text = "Here is an example of a CAS from Swansea University."
    doc = Document(id="doc", name="cas.pdf", path="unused", sha256="d"*64,
                   pages=[Page(number=1, text=text, method="pdf_text")])
    case = Case(id="unit", documents=[doc])
    errors = apply_proposal(case, Proposal(facts=[Candidate(key="cas_name", value="Swansea University",
        source_id="doc", page=1, quote=text)]), {})
    assert errors and not case.facts


def test_missing_page_tool_result_allows_model_to_stop_cleanly():
    calls = []
    def respond(messages, info):
        calls.append(1)
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart("read_evidence", {"document_id": "doc", "page": 2})])
        assert any("not supplied" in str(p.content) for m in messages for p in m.parts
                   if getattr(p, "part_kind", "") == "tool-return")
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"facts": [], "documents": []})])
    doc = Document(id="doc", name="input.pdf", path="unused", sha256="d"*64,
                   pages=[Page(number=1, text="Page 1 of 2", method="pdf_text")])
    trace = {}
    result = extract(Case(id="unit", documents=[doc]), CaseEvent(case_id="unit", event_id="e"),
                     [doc], trace, mode="offline", model_override=FunctionModel(respond))
    assert not result.facts and trace["tools"][0]["page"] == 2
