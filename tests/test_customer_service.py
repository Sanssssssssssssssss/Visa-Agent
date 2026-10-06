"""Business boundaries introduced by vision, examples and novice conversations."""

import hashlib
import json

from PIL import Image
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.models.test import TestModel

from visa_agent.conversation import language_for, material_progress, reply_for
from visa_agent.diagnostics import document_issues
from visa_agent.documents import read_document
from visa_agent.evidence import Evidence, apply_proposal, validate_value
from visa_agent.rules import evaluate, status_for
from visa_agent.service import VisaService
from visa_agent.types import Candidate, Case, CaseEvent, Check, Document, DocumentTag, Fact, Page, Proposal, Route
from visa_agent.vision import log_part, visual_inputs


def test_sample_cannot_advance_real_case_or_be_reclassified_by_model():
    doc = Document(id="d", path="unused", name="sample.pdf", sha256="a"*64,
                   content_role="sample", kind="passport", language="en",
                   pages=[Page(number=1, text="Passport name: Alex River", method="pdf_text")])
    case = Case(id="real", documents=[doc])
    apply_proposal(case, Proposal(documents=[DocumentTag(document_id="d", kind="passport", language="en", content_role="evidence")],
        facts=[Candidate(key="passport_name", value="Alex River", quote="Passport name: Alex River", source_id="d", page=1)]), {})
    assert case.documents[0].content_role == "sample"
    assert Evidence(case).get("passport_name") is None
    assert any(c.id == "sample:d" and c.status == "fail" for c in evaluate(case))
    case.test_mode = True
    assert Evidence(case).get("passport_name") == "Alex River"
    case.documents[0].content_role = "unrelated"
    assert Evidence(case).get("passport_name") is None  # Demo cannot make rubbish valid.


def test_image_bytes_and_rendered_pdf_reach_prompt_without_binary_logs(tmp_path):
    from reportlab.pdfgen import canvas
    jpg = tmp_path / "photo.jpg"
    Image.new("RGB", (200, 200), "white").save(jpg)
    pdf = tmp_path / "text.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(30, 700, "VISIBLE DOCUMENT TEST")
    c.save()
    docs = [Document(id=str(i), name=p.name, path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                     pages=[Page(number=1, text="test", method="pdf_text")]) for i, p in enumerate([jpg, pdf])]
    trace = {}
    parts = visual_inputs(docs, trace)
    assert parts[1].data == jpg.read_bytes()
    assert parts[3].data.startswith(b"\x89PNG")
    logged = log_part(UserPromptPart(["ocr", *parts]))
    serialized = json.dumps(logged)
    assert "image_sha256" in serialized and "base64" not in serialized
    assert [r["method"] for r in trace["visual_inputs"]] == ["original_image", "rendered_pdf_page"]
    # The tool schema cannot alter case mode, approval or customer language.
    assert not {"test_mode", "approval", "language"} & Proposal.model_fields.keys()


def test_visual_page_limit_is_explicit(tmp_path):
    p = tmp_path / "image.png"
    Image.new("RGB", (32, 32)).save(p)
    doc = Document(id="d", path=str(p), name=p.name, sha256="a"*64,
                   pages=[Page(number=i, text="test", method="ocr") for i in range(1, 9)])
    trace = {}
    visual_inputs([doc], trace)
    assert sum(r["sent"] for r in trace["visual_inputs"]) == 6
    assert [r["page"] for r in trace["visual_inputs"] if not r["sent"]] == [7, 8]


def test_vision_disagreement_blocks_source_grounded_value():
    doc = Document(id="d", path="unused", name="bank.png", sha256="a"*64,
                   pages=[Page(number=1, text="Balance 5000", method="ocr")])
    case = Case(id="unit", documents=[doc])
    proposal = Proposal(documents=[DocumentTag(document_id="d", kind="bank_statement", language="en",
        needs_visual_review=True, visual_observation="Visible value differs from OCR")],
        facts=[Candidate(key="bank_minimum", value="5000", quote="Balance 5000", page=1, source_id="d")])
    apply_proposal(case, proposal, {})
    assert Evidence(case).get("bank_minimum") is None
    assert document_issues(doc)[0]["code"] == "vision_ocr_disagreement"


def test_language_is_from_customer_not_document_or_nationality(tmp_path):
    assert language_for("用英文回复，谢谢") == "en"
    assert language_for("Please reply in Chinese") == "zh"
    assert language_for("Alex", "zh") == "zh"
    service = VisaService(tmp_path, "live", model_override=TestModel(call_tools=[], custom_output_args={"intent": "getting_started"}))
    service.store.create("cn")
    result = service.handle_event(CaseEvent(case_id="cn", event_id="e1", text="我人在中国，第一次申请，要什么材料？"))
    case = service.store.get("cn")
    assert case.language == "zh" and not case.test_mode
    assert Evidence(case).get("nationality") is None
    assert "护照" in result.reply and "gov.uk" in result.reply and "材料进度" in result.reply


def test_progress_never_counts_unknown_or_not_applicable_as_a_checked_material():
    checks = [Check(id=id, status=status, source="unit", message="test") for id, status in
              [("passport_name", "pass"), ("passport_number", "unknown"), ("passport_valid", "pass"),
               ("finance_submission", "not_applicable"), ("tb_applicability", "unknown")]]
    case = Case(id="p", route=Route.STUDENT, checks=checks, language="en")
    assert material_progress(case)["checked"] == 0
    assert material_progress(case)["total"] == 2
    case.checks[1].status = "pass"
    assert material_progress(case)["checked"] == 1
    case.pending_error = "provider failed"
    assert material_progress(case)["checked"] == 0


def test_inside_uk_reply_requests_status_without_claiming_switch_eligibility():
    case = Case(id="uk", language="en", facts=[Fact(id="f", key="application_location", value="inside_uk",
                quote="inside the UK", source_id="message:e")])
    case.checks = evaluate(case)
    case.status = status_for(case.checks)
    reply = reply_for(case, intent="how_to_apply")
    assert "current visa type and expiry" in reply and "adviser" in reply
    assert "outside the UK" in reply and "NEEDS_HUMAN" not in reply


def test_garbage_file_records_recovery_category(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"junk")
    doc = read_document(p, hashlib.sha256(p.read_bytes()).hexdigest(), p.name)
    issue = document_issues(doc)[0]
    assert issue["code"] == "invalid_file" and issue["next_action"] == "reupload"


def test_short_evidence_survives_long_customer_reply_history():
    from visa_agent.agent import build_context
    case = Case(id="ctx", history=[{"event_id": str(i), "text": "old "*300, "reply": "old "*400} for i in range(6)])
    doc = Document(id="d", path="unused", name="short.pdf", sha256="a"*64,
                   pages=[Page(number=1, text="Bank details "*50, method="pdf_text")])
    prompt, _ = build_context(case, CaseEvent(case_id="ctx", event_id="new"), [doc])
    data = json.loads(prompt)
    assert data["new_documents"][0]["pages"][0]["text"] == doc.pages[0].text


def test_own_money_is_canonical_only_with_explicit_self_funding_quote():
    import pytest
    assert validate_value("funding", "own money", "I am paying using my own money.") == "self"
    for quote in ("My employer pays.", "I am not using my own money.", "My parents provide their own money."):
        with pytest.raises(ValueError):
            validate_value("funding", "own money", quote)


def test_offline_transport_cannot_change_case_to_demo(tmp_path):
    service = VisaService(tmp_path, "offline")
    service.store.create("real")
    service.handle_event(CaseEvent(case_id="real", event_id="e", text="route: visitor"))
    assert not service.store.get("real").test_mode


def test_name_conflict_keeps_material_category_pending():
    checks = [Check(id=k, status="pass", source="test", message="ok")
              for k in ("passport_name", "passport_number", "passport_valid", "finance")]
    checks.append(Check(id="name:bank_holder", status="fail", source="test", message="mismatch"))
    p = material_progress(Case(id="x", route=Route.VISITOR, checks=checks))
    assert p["total"] == 2 and p["checked"] == 1
