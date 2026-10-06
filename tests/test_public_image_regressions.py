"""Regressions found with public statement scans; no network or paid model."""

from PIL import Image
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from visa_agent.agent import build_context
from visa_agent.documents import pagination_problems, read_document
from visa_agent.evidence import apply_proposal
from visa_agent.rules import evaluate
from visa_agent.service import VisaService
from visa_agent.types import Candidate, Case, CaseEvent, Document, Page, Proposal


def test_image_page_counter_blocks_missing_pages_and_minimum(tmp_path, monkeypatch):
    path = tmp_path / "scan.png"
    Image.new("RGB", (40, 40), "white").save(path)
    monkeypatch.setattr("visa_agent.documents.image_text", lambda image, number: Page(
        number=number, text="Page 1 of 3\nOpening balance GBP 50.00", method="ocr", confidence=0.99))
    doc = read_document(path, "a" * 64, path.name)
    assert any("pagination incomplete" in p for p in doc.problems)
    case = Case(id="unit", documents=[doc])
    errors = apply_proposal(case, Proposal(facts=[Candidate(
        key="bank_minimum", value="50", source_id=doc.id, page=1, quote="Opening balance GBP 50.00")]), {})
    assert errors and not case.facts
    assert any(c.id.startswith("pagination:") and c.status == "unknown" for c in evaluate(case))


def test_complete_document_counters_and_other_numbers():
    def page(number):
        return Page(number=number, text=f"Page {number} of 3\nTransaction 10", method="pdf_text")
    assert not pagination_problems([page(1), page(2), page(3)])
    assert pagination_problems([page(1), page(3)])
    assert pagination_problems([page(1), page(1), page(3)])
    assert not pagination_problems([Page(number=1, text="Balance 100 of 200", method="pdf_text")])


def test_context_capacity_is_a_persistent_review_issue_not_a_failed_event(tmp_path, monkeypatch):
    page = Page(number=1, text="Transaction details. " * 1800, method="pdf_text")
    doc = Document(id="doc", name="long.pdf", path="unused", sha256="a" * 64, pages=[page])
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(source)
    monkeypatch.setattr("visa_agent.service.read_document", lambda *args: doc.model_copy(deep=True))
    calls = []

    def respond(messages, info):
        calls.append(1)
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart("read_evidence", {"document_id": "doc", "page": 1})])
        assert any("NOT supplied" in str(p.content) for m in messages for p in m.parts
                   if getattr(p, "part_kind", "") == "tool-return")
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"facts": [], "documents": []})])

    service = VisaService(tmp_path / "store", "offline", model_override=FunctionModel(respond))
    service.store.create("unit")
    event = CaseEvent(case_id="unit", event_id="input", attachments=[str(source)])
    result = service.handle_event(event)
    assert not result.error and result.status == "NEEDS_HUMAN"
    case = service.store.get("unit")
    assert any(c.id == "context:doc" for c in case.checks)
    assert service.store.events("unit")[0]["status"] == "done"
    restarted = VisaService(tmp_path / "store", "offline")
    assert restarted.handle_event(event).duplicate
    refreshed = restarted.review_case("unit", case.version, "refresh", "Check persisted limitation")
    assert refreshed.status == "NEEDS_HUMAN"
    assert any(c.id == "context:doc" for c in refreshed.checks)
    assert len(calls) == 2


def test_truncated_preview_explicitly_reports_original_length():
    import json
    doc = Document(id="doc", name="long.pdf", path="unused", sha256="a" * 64,
                   pages=[Page(number=1, text="Long financial evidence. " * 400, method="pdf_text")])
    prompt, remaining = build_context(Case(id="unit", documents=[doc]),
                                     CaseEvent(case_id="unit", event_id="input"), [doc])
    preview = json.loads(prompt)["new_documents"][0]["pages"][0]
    assert preview["truncated"] and preview["total_chars"] == len(doc.pages[0].text)
    assert remaining > 0
