"""Validate model proposals before changing the case; retain conflicting evidence."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from .store import digest
from .types import BOOL_FIELDS, DATE_FIELDS, FIELDS, NUMBER_FIELDS, Case, Fact, Proposal


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def validate_value(key: str, value: str, quote: str) -> str:
    value = value.strip()
    if key not in FIELDS or not value or value.lower() in {"unknown", "null", "none", "n/a"}:
        raise ValueError(f"Unsupported or empty field: {key}")
    if re.search(r"\*{2,}|\b[xX]{3,}\b|\b(?:your|name|number|date)\b.*\bhere\b", value, re.I):
        raise ValueError(f"Placeholder is not an applicant fact: {key}")
    # Normalize only explicit equivalent phrases; do not geocode an address or infer a region.
    countries = {
        "India": ["India", "Indian"], "China": ["China", "Chinese", "中国"],
        "Japan": ["Japan", "Japanese", "日本"], "Singapore": ["Singapore", "Singaporean"],
        "United States": ["United States", "USA", "American"],
        "Canada": ["Canada", "Canadian"], "Australia": ["Australia", "Australian"],
    }
    enums = {
        "nationality": countries,
        "residence_country": countries,
        "application_location": {
            "outside_uk": ["outside_uk", "outside UK", "outside the UK", "英国境外"],
            "inside_uk": ["inside_uk", "inside UK", "inside the UK", "英国境内"],
        },
        "study_location": {
            "london": ["london", "伦敦"],
            "outside_london": ["outside_london", "outside London", "伦敦以外"],
        },
        "bank_currency": {"GBP": ["GBP", "£", "pounds sterling"],
                          "CNY": ["CNY", "RMB", "人民币"],
                          "USD": ["USD", "US dollars"], "EUR": ["EUR", "€"]},
    }
    if key in enums:
        for canonical, aliases in enums[key].items():
            if any(normalized(value) == normalized(alias) for alias in aliases):
                if not any(normalized(alias) in normalized(quote) for alias in aliases):
                    raise ValueError(f"Value not grounded in quote: {key}")
                return canonical
        # Other ISO currency codes remain explicit values, with no conversion inference.
        if key in {"application_location", "study_location"}:
            raise ValueError(f"Unsupported location value: {key}")
    if key == "funding":
        # Models sometimes return only the tail of "my own money". Canonicalize
        # that value, then still require explicit self-funding in the source quote.
        if value.casefold() in {"own money", "own funds"}:
            value = "self"
        patterns = {"self": r"\b(self(?:[- ]funded)?|my own (?:money|funds)|my savings|myself)\b|自费|本人出资|(?:我|本人)自己(?:支付|付|承担)",
                    "employer": r"\bemployer(?:[- ]funded)?\b|雇主"}
        matches = [kind for kind, pattern in patterns.items() if re.search(pattern, value, re.I)]
        if len(matches) == 1:
            pattern = patterns[matches[0]]
            quote_kinds = [kind for kind, pat in patterns.items() if re.search(pat, quote, re.I)]
            if (quote_kinds != matches or re.search(r"\b(not|parents?|loan|scholarship|sponsor)\b|不是|并非|不由|不打算|父母|贷款|奖学金", quote, re.I)):
                raise ValueError("Funding source is negative or ambiguous; adviser review needed")
            if re.search(pattern, quote, re.I):
                return matches[0]
    if key in DATE_FIELDS:
        # A four-digit leading year makes this slash format unambiguous.
        if re.fullmatch(r"\d{4}/\d{2}/\d{2}", value):
            value = value.replace("/", "-")
        parsed = date.fromisoformat(value)
        formats = [parsed.isoformat(), parsed.strftime("%d/%m/%Y"),
                   parsed.strftime("%d %B %Y"), parsed.strftime("%Y/%m/%d")]
        if not any(normalized(item) in normalized(quote) for item in formats):
            raise ValueError(f"Date value not grounded in quote: {key}")
    elif key in NUMBER_FIELDS:
        try:
            number = Decimal(value.replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid number: {key}") from exc
        if not number.is_finite() or number < 0:
            raise ValueError(f"Invalid non-negative amount: {key}")
        numbers = re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", quote)
        if not any(Decimal(n.replace(",", "")) == number for n in numbers):
            raise ValueError(f"Number not grounded in quote: {key}")
        value = format(number.normalize(), "f")
    elif key in BOOL_FIELDS:
        value = {"0": "false", "1": "true", "no": "false", "yes": "true"}.get(value.lower(), value)
        if value not in {"true", "false"}:
            raise ValueError(f"Boolean must be true/false: {key}")
        negative = bool(re.search(r"\b(false|no|not|none)\b|否|不需要|没有", quote, re.I))
        positive = bool(re.search(r"\b(true|yes|required|confirmed)\b|是|需要", quote, re.I))
        if (value == "true" and (not positive or negative)) or (value == "false" and not negative):
            raise ValueError(f"Boolean not grounded in quote: {key}")
    elif key == "route":
        aliases = {"visitor": ["visitor", "tourism", "旅游", "访问"],
                   "student": ["student", "study", "学生", "留学"],
                   "skilled_worker": ["skilled_worker", "skilled worker", "技术工作"]}
        if value not in aliases or not any(normalized(a) in normalized(quote)
                                           for a in aliases[value]):
            raise ValueError("Route not supported by the quoted intent")
    elif normalized(value) not in normalized(quote):
        aliases = {
            "outside_uk": ["outside UK", "outside the UK", "英国境外"],
            "outside_london": ["outside London", "伦敦以外"],
            "self": ["my own", "myself", "自费", "本人"],
            "China": ["中国"], "India": ["印度"], "Japan": ["日本"],
        }
        if not any(normalized(a) in normalized(quote) for a in aliases.get(value, [])):
            raise ValueError(f"Value not grounded in quote: {key}")
    return value


def apply_proposal(case: Case, proposal: Proposal, message_sources: dict[str, str]) -> list[str]:
    docs = {d.id: d for d in case.documents}
    for tag in proposal.documents:
        if tag.document_id not in docs:
            raise ValueError("Model referenced a document outside this case")
        doc = docs[tag.document_id]
        if not doc.rejected:
            doc.kind, doc.language = tag.kind, tag.language
            # A visible test watermark cannot be overruled by a model tag.
            if doc.content_role != "sample" and tag.content_role != "uncertain":
                doc.content_role = tag.content_role
            if tag.needs_visual_review:
                problem = "Visual/OCR discrepancy: " + (tag.visual_observation or "Compare original and extracted text")
                if problem not in doc.problems:
                    doc.problems.append(problem)
    rejected = []
    for candidate in proposal.facts:
        try:
            if candidate.source_id.startswith("message:"):
                text = message_sources.get(candidate.source_id, "")
                if candidate.page is not None:
                    raise ValueError("Message references cannot contain a page")
            else:
                doc = docs.get(candidate.source_id)
                if doc is None or doc.rejected:
                    raise ValueError("Unknown or rejected source")
                page = next((p for p in doc.pages if p.number == candidate.page), None)
                text = page.text if page else ""
                if candidate.key == "bank_minimum" and any(
                    p.startswith("Declared pagination incomplete") for p in doc.problems
                ):
                    raise ValueError("Incomplete statement cannot establish the full-period minimum")
            if not text or normalized(candidate.quote) not in normalized(text):
                raise ValueError("Supporting quote not found in source")
            if candidate.key in {"applicant_name", "passport_name", "employment_name", "bank_holder", "cas_name", "cos_name", "tb_name"}:
                if candidate.key == "bank_holder" and re.fullmatch(
                    r"(?:e?savings|current|checking|business|deposit|term|joint)\s+account|account\s+(?:holder|name|type)",
                    candidate.value.strip(), re.I,
                ):
                    raise ValueError("Account type or field label is not an account holder")
                if re.search(r"\b(?:university|college|ltd|limited|plc|inc)\b|^bank\s+of\b", candidate.value, re.I):
                    raise ValueError("Organisation is not a personal applicant name; review the subject")
                signature = re.search(r"\b(?:yours sincerely|yours faithfully|signed by|authorised signatory)\b", text, re.I)
                if (signature and normalized(candidate.value) not in normalized(text[:signature.start()])
                        and normalized(candidate.value) in normalized(text[signature.start():])):
                    raise ValueError("Signatory is not an applicant identity")
            candidate.value = validate_value(candidate.key, candidate.value, candidate.quote)
            fact_id = digest(candidate.model_dump())[:20]
            if not any(f.id == fact_id for f in case.facts):
                case.facts.append(Fact(id=fact_id, **candidate.model_dump()))
        except ValueError as exc:
            rejected.append(f"{candidate.key}: {exc}")
    return rejected


class Evidence:
    def __init__(self, case: Case):
        self.case = case
        self.docs = {d.id: d for d in case.documents}

    def admissible(self, doc) -> bool:
        return not (doc.rejected or doc.problems or doc.content_role == "unrelated"
                    or (doc.content_role == "sample" and not self.case.test_mode))

    def facts(self, key: str, kinds: set[str] | None = None) -> list[Fact]:
        result = []
        for fact in self.case.facts:
            # "My passport name is X" is also a self-reported applicant name.
            # Retain the original field/source, and never promote it to file evidence.
            own_passport_name = (key == "applicant_name" and fact.key == "passport_name"
                and fact.source_id.startswith("message:")
                and re.search(r"我的护照(?:上(?:的)?)?姓名(?:是|为)|\bmy passport name is\b", fact.quote, re.I)
                and not re.search(r"不是|并非|\bnot\b", fact.quote, re.I))
            if not fact.active or (fact.key != key and not own_passport_name) or (fact.confidence == "low" and not fact.confirmed_by):
                continue
            doc = self.docs.get(fact.source_id)
            if doc and not self.admissible(doc):
                continue
            if kinds is not None and (doc is None or doc.kind not in kinds):
                continue
            result.append(fact)
        return result

    def get(self, key: str, kinds: set[str] | None = None) -> str | None:
        values = {f.value for f in self.facts(key, kinds)}
        return next(iter(values)) if len(values) == 1 else None

    def number(self, key: str, kinds: set[str] | None = None) -> Decimal | None:
        value = self.get(key, kinds)
        return Decimal(value) if value is not None else None

    def day(self, key: str, kinds: set[str] | None = None) -> date | None:
        value = self.get(key, kinds)
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None
