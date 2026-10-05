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
    if key in DATE_FIELDS:
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
            if not text or normalized(candidate.quote) not in normalized(text):
                raise ValueError("Supporting quote not found in source")
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

    def facts(self, key: str, kinds: set[str] | None = None) -> list[Fact]:
        result = []
        for fact in self.case.facts:
            if not fact.active or fact.key != key or (fact.confidence == "low" and not fact.confirmed_by):
                continue
            doc = self.docs.get(fact.source_id)
            if doc and (doc.rejected or doc.problems):
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
