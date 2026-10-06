"""Source format is independent of whether all required values were extracted."""
from pathlib import Path
import hashlib

import pytest

from visa_agent.documents import is_evidence_field_list, read_document
from visa_agent.evidence import Evidence, apply_proposal, validate_value
from visa_agent.rules import evaluate
from visa_agent.types import Case, Candidate, Document, DocumentTag, Page, Proposal

DATA = Path(__file__).resolve().parents[1] / "datasets/document-quality"


@pytest.mark.parametrize("name", ["passport.pdf", "bank.pdf", "employment.pdf", "passport-notes.jpg"])
def test_notes_cannot_be_promoted_by_model_tag_or_used_for_passport(name):
    path = DATA / name
    doc = read_document(path, hashlib.sha256(path.read_bytes()).hexdigest(), path.name)
    assert doc.content_role == "self_report"
    case = Case(id="x", documents=[doc])
    apply_proposal(case, Proposal(documents=[DocumentTag(document_id=doc.id, kind="passport", language="en", content_role="evidence")]), {})
    assert doc.content_role == "self_report" and not Evidence(case).admissible(doc)
    assert any(c.id == f"self_report:{doc.id}" and c.status == "unknown" for c in evaluate(case))


def test_uncertain_document_with_correct_values_remains_unusable():
    doc = Document(id="d", name="passport.pdf", sha256="x", path="unused", kind="passport", language="en",
                   pages=[Page(number=1, text="Name: Lin Chen", method="pdf_text")])
    case = Case(id="x", documents=[doc])
    apply_proposal(case, Proposal(facts=[Candidate(key="passport_name", value="Lin Chen", source_id="d", page=1, quote="Name: Lin Chen")]), {})
    assert len(case.facts) == 1  # Retain the source; do not silently delete it.
    assert Evidence(case).get("passport_name", {"passport"}) is None
    assert any(c.id == "uncertain:d" for c in evaluate(case))


def test_text_letters_and_applicant_travel_plans_are_not_blanket_rejected():
    assert not is_evidence_field_list("Harbor Bank\nAccount holder: Lin Chen\nClosing balance: GBP 40000")
    assert not is_evidence_field_list("purpose: tourism\ntravel_start: 2026-11-01\ntravel_end: 2026-11-10")
    doc = Document(id="d", name="bank.pdf", sha256="x", path="unused", kind="bank_letter", language="en", content_role="evidence")
    assert Evidence(Case(id="x", documents=[doc])).admissible(doc)


def test_old_persisted_evidence_tag_cannot_bypass_new_format_gate():
    doc = Document(id="old", name="passport.pdf", path="unused", sha256="x", kind="passport", language="en",
                   content_role="evidence", pages=[Page(number=1, method="pdf_text",
                       text="passport_name: Lin Chen\npassport_number: N12345067\npassport_expiry: 2036-01-01")])
    case = Case(id="x", documents=[doc])
    assert not Evidence(case).admissible(doc)
    assert any(c.id == "self_report:old" and c.status == "unknown" for c in evaluate(case))
    assert doc.content_role == "self_report"


def test_employment_case_equivalence_keeps_source_grounding_and_english_grade_is_not_confirmation():
    assert validate_value("employment_status", "Employed", "Status: Employed") == "employed"
    with pytest.raises(ValueError):
        validate_value("employment_status", "Employed", "Status: retired")
    with pytest.raises(ValueError):
        validate_value("employment_status", "Employed", "Status: unemployed")
    with pytest.raises(ValueError):
        validate_value("english_confirmed", "true", "CEFR English level B2")
