"""Small, inspectable error categories for local traces, never customer instructions."""

import re


def document_issues(doc):
    rows = []
    patterns = [
        ("low OCR confidence", "ocr_low_confidence", "ocr", "reupload_or_review"),
        ("unreadable", "no_readable_text", "read", "reupload"),
        ("Declared pagination", "page_set_unverified", "read", "upload_complete_pdf"),
        ("Model context", "context_limit", "model", "adviser_full_read"),
        ("Visual/OCR", "vision_ocr_disagreement", "extract", "compare_original"),
        ("Visual input", "visual_input_unavailable", "vision", "split_or_review"),
        ("encrypted", "encrypted_pdf", "read", "export_unlocked_copy"),
        ("20 pages", "page_limit", "read", "split_file"),
        ("pixel", "pixel_limit", "read", "resize_image"),
    ]
    for detail in doc.problems:
        code, stage, action = "invalid_file", "read", "reupload"
        for pattern, code_candidate, stage_candidate, action_candidate in patterns:
            if pattern.lower() in detail.lower():
                code, stage, action = code_candidate, stage_candidate, action_candidate
                break
        page = re.search(r"page (\d+)", detail)
        rows.append({"code": code, "stage": stage, "document_id": doc.id,
                     "page": int(page[1]) if page else None, "detail": detail, "next_action": action})
    if doc.content_role in {"sample", "unrelated"}:
        rows.append({"code": "sample_material" if doc.content_role == "sample" else "irrelevant_material",
                     "stage": "classify", "document_id": doc.id, "next_action": "supply_applicant_evidence"})
    if doc.content_role in {"self_report", "uncertain"}:
        rows.append({"code": "self_report_not_evidence" if doc.content_role == "self_report" else "evidence_type_unconfirmed",
                     "stage": "classify", "document_id": doc.id, "next_action": "supply_original_document"})
    return rows


def turn_diagnostics(case, trace):
    rows = [row for d in case.documents if not d.rejected for row in document_issues(d)]
    rows.extend({"code": tool["error_code"], "stage": "tool", "document_id": tool.get("document_id"),
                 "page": tool.get("page"), "detail": tool["result"], "next_action": "inspect_tool_arguments"}
                for tool in trace.get("tools", []) if tool.get("error_code"))
    for rejected in trace.get("rejected_candidates", []):
        code = "candidate_invalid"
        for marker, name in [("quote not found", "quote_missing"), ("not grounded", "value_not_grounded"),
                             ("Placeholder", "placeholder_value"), ("not an account holder", "wrong_field_role"),
                             ("not a personal", "wrong_field_role"), ("Incomplete statement", "incomplete_evidence")]:
            if marker.lower() in rejected.lower():
                code = name
                break
        rows.append({"code": code, "stage": "grounding", "detail": rejected,
                     "next_action": "compare_quote_and_original"})
    rows.extend({"code": row["reason"], "stage": "grounding", "field": row["key"],
                 "source_id": row["source_id"], "quote": row["quote"],
                 "next_action": "confirm_application_location" if row["reason"] == "application_location_unconfirmed" else "confirm_full_date"}
                for row in trace.get("unconfirmed_candidates", []))
    for check in case.checks:
        if check.status in {"fail", "unknown"}:
            rows.append({"code": "rule_failed" if check.status == "fail" else "rule_unresolved",
                         "stage": "check", "check_id": check.id, "source": check.source,
                         "evidence": check.evidence, "detail": check.message,
                         "next_action": "adviser_review" if check.human else "request_information"})
    if trace.get("error"):
        error = trace["error"]
        code = "budget_exhausted" if "budget" in error.lower() else (
            "no_progress" if "NoProgress" in error else "provider_error" if any(x in error for x in ("API", "HTTP", "Timeout")) else "processing_error")
        rows.append({"code": code, "stage": "runtime", "detail": error, "next_action": "operator_review_then_retry"})
    return rows
