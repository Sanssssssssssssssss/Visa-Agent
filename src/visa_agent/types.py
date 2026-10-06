"""Small data contracts. Every accepted fact keeps its original source."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Status(StrEnum):
    WAIT_USER = "WAIT_USER"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    BLOCKED = "BLOCKED"
    READY = "READY_FOR_REVIEW"
    COMPLETE = "COMPLETE"


class Route(StrEnum):
    VISITOR = "visitor"
    STUDENT = "student"
    WORKER = "skilled_worker"


class CaseEvent(StrictModel):
    case_id: str
    event_id: str
    kind: Literal["message", "upload", "tick"] = "message"
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    text: str = Field(default="", max_length=12000)
    attachments: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("case_id", "event_id")
    @classmethod
    def safe_identifier(cls, value: str) -> str:
        import re
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
            raise ValueError("IDs must contain 1-80 ASCII letters, numbers, '_' or '-'")
        return value

    @field_validator("at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Event time must include a timezone")
        return value.astimezone(timezone.utc)


class Page(StrictModel):
    number: int
    text: str
    method: Literal["pdf_text", "ocr"]
    confidence: float | None = None


class Document(StrictModel):
    id: str
    name: str
    sha256: str
    path: str
    pages: list[Page] = Field(default_factory=list)
    kind: str = "unknown"
    language: str = "unknown"
    problems: list[str] = Field(default_factory=list)
    rejected: bool = False
    content_role: Literal["evidence", "sample", "unrelated", "uncertain"] = "uncertain"


class Candidate(StrictModel):
    key: str
    value: str
    source_id: str = Field(description="message:<event_id> or exact document id")
    page: int | None = Field(default=None, ge=1)
    quote: str = Field(min_length=1, max_length=1000, description="Exact supporting excerpt")
    confidence: Literal["high", "low"] = "high"


class Fact(Candidate):
    id: str
    active: bool = True
    confirmed_by: str | None = None


class DocumentTag(StrictModel):
    document_id: str
    kind: Literal[
        "passport", "bank_statement", "bank_letter", "employment", "travel_plan",
        "cas", "cos", "english", "tb", "atas", "translation", "sponsorship", "unknown",
    ]
    language: Literal["en", "cy", "zh", "other", "unknown"]
    content_role: Literal["evidence", "sample", "unrelated", "uncertain"] = "uncertain"
    visual_observation: str = Field(default="", max_length=300)
    needs_visual_review: bool = False


class Proposal(StrictModel):
    facts: list[Candidate] = Field(default_factory=list, max_length=100)
    documents: list[DocumentTag] = Field(default_factory=list, max_length=30)
    intent: Literal["getting_started", "how_to_apply", "materials", "status", "continue", "other"] = "continue"


class Check(StrictModel):
    id: str
    status: Literal["pass", "fail", "unknown", "not_applicable"]
    message: str
    source: str
    human: bool = False
    evidence: list[str] = Field(default_factory=list)


class Guidance(StrictModel):
    actions: list[str] = Field(default_factory=list, max_length=3,
                              description="Existing unresolved check IDs, in priority order")
    explanation: Literal["continue", "how_to_apply", "materials"] = "continue"
    approach: Literal["neutral", "step_by_step", "explain_material"] = "neutral"
    warn_material_risk: bool = False
    delivery_decision: Literal["continue", "deliver"] = "continue"


class Approval(StrictModel):
    version: int
    manifest_hash: str
    reviewer: str
    notes: str
    at: str = Field(default_factory=now_utc)


class AutomaticCompletion(StrictModel):
    version: int
    manifest_hash: str
    decision_run_id: str
    # Historical records used a model decision; new collection records use checks.
    basis: Literal["model_guidance", "checklist"] = "model_guidance"
    at: str = Field(default_factory=now_utc)


class Case(StrictModel):
    id: str
    version: int = 0
    route: Route | None = None
    status: Status = Status.WAIT_USER
    rule_version: str = ""
    facts: list[Fact] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    extraction_issues: dict[str, list[str]] = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list)
    reviews: list[dict] = Field(default_factory=list)
    approval: Approval | None = None
    automatic_completion: AutomaticCompletion | None = None
    hitl_enabled: bool = True
    pack_path: str | None = None
    last_contact: str = Field(default_factory=now_utc)
    last_reminder: str | None = None
    reminder_count: int = 0
    pending_error: str | None = None
    language: Literal["zh", "en"] = "zh"
    test_mode: bool = False
    conversation_closed: bool = False
    history_count: int = 0


class TurnResult(StrictModel):
    case_id: str
    version: int
    status: Status
    reply: str
    run_id: str
    error: str | None = None
    duplicate: bool = False
    pack_path: str | None = None


# A deliberately finite vocabulary: extracted text cannot invent workflow controls.
FIELDS = {
    "route", "applicant_name", "nationality", "age", "application_location",
    "application_date", "dependants", "previous_refusal", "purpose", "funding",
    "residence_country", "residence_months", "stay_months", "travel_end", "travel_start",
    "passport_name", "passport_number", "passport_expiry", "bank_name", "bank_holder",
    "bank_currency", "bank_minimum", "bank_start", "bank_end", "trip_budget",
    "employer", "employment_name", "salary", "return_reason", "cas_reference",
    "cas_name", "tuition_due", "study_months", "study_location", "atas_required",
    "english_confirmed", "cos_reference", "cos_name", "sponsor_name", "sponsor_licence",
    "job_title", "occupation_code", "maintenance_certified", "english_level",
    "tb_name", "tb_expiry", "tb_clear", "atas_reference", "translation_for",
    "translator_name", "translation_date", "translator_contact", "translation_accurate",
    "translator_signed", "financial_evidence_requested",
}

DATE_FIELDS = {"application_date", "travel_start", "travel_end", "passport_expiry",
               "bank_start", "bank_end", "tb_expiry", "translation_date"}
BOOL_FIELDS = {"dependants", "previous_refusal", "atas_required", "english_confirmed",
               "maintenance_certified", "tb_clear", "translation_accurate",
               "translator_signed", "financial_evidence_requested"}
NUMBER_FIELDS = {"age", "residence_months", "stay_months", "bank_minimum", "trip_budget",
                 "salary", "tuition_due", "study_months"}
