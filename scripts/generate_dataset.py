"""Generate labelled synthetic evidence, independent expected facts, and 15 cases.

Run once before acceptance. --force must be explicit because acceptance freezes hashes.
No model, real applicant information, official logos, seals or real document numbers.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import time

from PIL import Image, ImageFilter
import pypdfium2 as pdfium
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
random.seed(20261005)
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def make_pdf(path, kind, fields, *, chinese=False, alternate=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=(595, 842), invariant=1)
    c.setTitle("SYNTHETIC TEST MATERIAL - NOT VALID FOR APPLICATION")
    c.setFillColorRGB(0.08, 0.30, 0.34)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(38, 800, "TEST EVIDENCE / " + kind.upper().replace("_", " "))
    c.setFont("Helvetica", 9)
    c.drawString(38, 778, "SYNTHETIC - fictitious people and institutions - not a valid document")
    c.setFillColorRGB(0.08, 0.08, 0.08)
    c.setFont("STSong-Light" if chinese else "Helvetica", 12)
    lines = [f"DOCUMENT_KIND: {kind}", f"LANGUAGE: {'zh' if chinese else 'en'}"]
    if chinese:
        lines += ["测试材料，仅用于软件验证，不可用于真实申请。", "申请人信息请逐项核对。"]
    pairs = list(fields.items())
    if alternate:
        pairs.reverse()
    lines.extend(f"{key}: {value}" for key, value in pairs)
    y = 745
    for line in lines:
        if y < 60:
            c.showPage()
            c.setFont("STSong-Light" if chinese else "Helvetica", 12)
            y = 780
        c.drawString(38 if not alternate else 60, y, line)
        y -= 24 if not alternate else 29
    c.setFont("Helvetica", 9)
    c.drawString(38, 32, "Visa Agent synthetic fixture | Seed 20261005 | English field labels aid inspection")
    c.save()


def raster(pdf, destination, variant="scan"):
    with pdfium.PdfDocument(pdf) as source:
        page = source[0]
        bitmap = page.render(scale=2)
        image = bitmap.to_pil().convert("RGB")
        bitmap.close()
        page.close()
    if variant == "rotate":
        image = image.rotate(3, expand=True, fillcolor="white")
    elif variant == "blur":
        image = image.resize((100, 140)).resize(image.size).filter(ImageFilter.GaussianBlur(12))
    elif variant == "crop":
        image = image.crop((0, 0, image.width, image.height // 3))
    if destination.suffix == ".pdf":
        image.save(destination, "PDF", resolution=144,
                   creationDate=time.gmtime(1791158400), modDate=time.gmtime(1791158400))
    else:
        image.save(destination, quality=88)


def case_documents(base, route, name, *, alternate=False, insufficient=False, maintenance=True):
    fields = {
        "identity": ("passport", {"passport_name": name, "passport_number": f"TEST-{random.randrange(100000,999999)}",
                                    "passport_expiry": "2037-02-02" if alternate else "2036-01-01"}),
        "funds": ("bank_statement", {"bank_name": "Fictional Example Bank", "bank_holder": name,
                                     "bank_currency": "GBP", "bank_minimum": "42000" if alternate else "40000",
                                     "bank_start": "2026-10-10" if insufficient else "2026-09-01" if alternate else "2026-08-01",
                                     "bank_end": "2026-10-15" if alternate else "2026-09-28"}),
    }
    if route == "visitor":
        fields["work"] = ("employment", {"employment_name": name, "employer": "Example Studio Ltd", "salary": "45000"})
    else:
        fields["health"] = ("tb", {"tb_name": name, "tb_clear": "true", "tb_expiry": "2027-02-01"})
    if route == "student":
        fields["school"] = ("cas", {"cas_name": name, "cas_reference": "TEST-CAS-2026",
                                    "tuition_due": "17500" if alternate else "16000", "study_months": "12",
                                    "study_location": "outside_london", "english_confirmed": "true",
                                    "atas_required": "false"})
    elif route == "skilled_worker":
        fields["sponsor"] = ("cos", {"cos_name": name, "cos_reference": "TEST-COS-2026",
                                     "sponsor_name": "Example Software Ltd", "sponsor_licence": "TEST-LICENCE",
                                     "job_title": "Software Developer", "occupation_code": "2134",
                                     "salary": "68000" if alternate else "65000", "maintenance_certified": str(maintenance).lower()})
        fields["language"] = ("english", {"english_level": "B2"})
        if maintenance or alternate:
            fields.pop("funds")
    docs, expected = [], {}
    for stem, (kind, data) in fields.items():
        path = base / (stem + ".pdf")
        make_pdf(path, kind, data, alternate=alternate)
        if alternate and stem == "identity":
            image = path.with_suffix(".jpg")
            raster(path, image)
            path = image
        docs.append(path)
        expected.update(data)
    return docs, expected


def message(route, name, alternate=False):
    fields = {"route": route, "applicant_name": name, "nationality": "China", "age": "30",
              "application_location": "outside_uk", "application_date": "2026-10-05",
              "dependants": "false", "previous_refusal": "false", "funding": "self",
              "travel_start": "2026-11-01", "residence_country": "China", "residence_months": "36"}
    if route == "visitor":
        fields.update(purpose="tourism", travel_end="2026-11-15", return_reason="return to my permanent job",
                      trip_budget="3000", stay_months="1")
    elif route == "student":
        fields.update(stay_months="12", financial_evidence_requested="true")
    else:
        fields.update(stay_months="24", funding="employer")
    if alternate:
        fields.update(application_date="2026-10-20", travel_start="2026-12-01")
        if route == "visitor":
            fields.update(travel_end="2026-12-17", trip_budget="3600")
    return "Hello, please help me prepare my UK application.\n" + "\n".join(f"{k}: {v}" for k, v in fields.items()), fields


def main(force=False):
    dataset = ROOT / "datasets"
    if (dataset / "freeze.json").exists() and not force:
        raise SystemExit("Dataset is frozen. Use --force only before starting a NEW acceptance run.")
    scenarios = []
    for split, routes in [("dev", ["visitor", "student", "skilled_worker"]),
                          ("holdout", ["visitor", "student", "skilled_worker"])]:
        for index, route in enumerate(routes):
            id = f"{split}_{route}"
            name = ["Lin Example", "Mei Example", "Kai Example"][index] if split == "dev" else ["Rui Sample", "Jia Sample", "Tao Sample"][index]
            docs, expected = case_documents(dataset / "materials" / id, route, name,
                                            alternate=split == "holdout", insufficient=id == "holdout_student",
                                            maintenance=True)
            text, declared = message(route, name, alternate=split == "holdout")
            events = [{"text": text, "attachments": []},
                      {"text": "Here is my identity document.", "attachments": [str(docs[0].relative_to(dataset))]},
                      {"text": "Here are the remaining supporting documents.",
                       "attachments": [str(p.relative_to(dataset)) for p in docs[1:]]}]
            if id == "holdout_skilled_worker":
                changed = {k: v for k, v in expected.items() if k in {
                    "cos_name", "cos_reference", "sponsor_name", "sponsor_licence", "job_title",
                    "occupation_code", "salary", "maintenance_certified"}}
                changed["maintenance_certified"] = "false"
                replacement = dataset / "materials" / id / "sponsor_updated.pdf"
                make_pdf(replacement, "cos", changed, alternate=True)
                events.append({"text": "My employer has replaced its sponsorship record. Please check the changed maintenance commitment.",
                               "attachments": [str(replacement.relative_to(dataset))],
                               "adviser_after": {"decision": "reject_document", "document_name": "sponsor.pdf",
                                                 "notes": "Synthetic adviser verifies that the updated CoS supersedes the old CoS."}})
                expected["maintenance_certified"] = "false"
            status = "WAIT_USER" if id in {"holdout_student", "holdout_skilled_worker"} else "READY_FOR_REVIEW"
            scenarios.append({"id": id, "split": split, "events": events, "expected_status": status,
                              "expected_blockers": ["finance"] if status == "WAIT_USER" else [],
                              "expected_fields": {**declared, **expected}, "exercise": "normal"})
    visitor = copy.deepcopy(scenarios[0])
    student = copy.deepcopy(scenarios[1])
    variants = ["ambiguous_route", "missing_document", "unreadable_image", "name_conflict",
                "funds_period", "missing_translation", "duplicate_event", "restart", "stale_approval"]
    for label in variants:
        s = copy.deepcopy(student if label == "funds_period" else visitor)
        s.update(id=f"dev_{label}", exercise=label, expected_status="WAIT_USER", expected_blockers=[])
        if label == "ambiguous_route":
            s["events"] = [{"text": "Hello, I want to travel to the UK. What do you need to know?", "attachments": []}]
            s["expected_fields"] = {}
            s["expected_blockers"] = ["route"]
        elif label == "missing_document":
            s["events"] = s["events"][:2]
            s["expected_fields"] = {k:v for k,v in s["expected_fields"].items()
                                     if not k.startswith("bank_") and k not in {"employer", "employment_name", "salary"}}
            s["expected_blockers"] = ["finance"]
        elif label == "unreadable_image":
            path = dataset / "materials" / "variants" / "unreadable.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (900, 1200), "white").save(path)
            s["events"][1]["attachments"] = [str(path.relative_to(dataset))]
            s["expected_fields"] = {k:v for k,v in s["expected_fields"].items() if not k.startswith("passport_")}
        elif label == "name_conflict":
            path = dataset / "materials" / "variants" / "different_identity.pdf"
            make_pdf(path, "passport", {"passport_name": "Other Example", "passport_number": "TEST-OTHER", "passport_expiry": "2036-01-01"})
            s["events"][1]["attachments"] = [str(path.relative_to(dataset))]
            s["expected_fields"].update(passport_name="Other Example", passport_number="TEST-OTHER")
            s["expected_status"] = "NEEDS_HUMAN"
            s["expected_blockers"] = ["name:applicant_name"]
        elif label == "funds_period":
            path = dataset / "materials" / "variants" / "short_period.pdf"
            data = {k:v for k,v in s["expected_fields"].items() if k.startswith("bank_")}
            data["bank_start"] = "2026-09-20"
            make_pdf(path, "bank_statement", data)
            s["events"][2]["attachments"] = [str(path.relative_to(dataset)) if "funds.pdf" in p else p for p in s["events"][2]["attachments"]]
            s["expected_fields"]["bank_start"] = "2026-09-20"
            s["expected_blockers"] = ["finance"]
        elif label == "missing_translation":
            path = dataset / "materials" / "variants" / "chinese_employment.pdf"
            data = {k:v for k,v in s["expected_fields"].items() if k in {"employment_name", "employer", "salary"}}
            make_pdf(path, "employment", data, chinese=True)
            s["events"][2]["attachments"] = [str(path.relative_to(dataset)) if "work.pdf" in p else p for p in s["events"][2]["attachments"]]
        else:
            s["expected_status"] = "READY_FOR_REVIEW"
        scenarios.append(s)
    for s in scenarios:
        expected = {k:s.pop(k) for k in ("expected_status", "expected_fields", "expected_blockers")}
        expected["event_states"] = ["WAIT_USER"] * len(s["events"])
        expected["event_states"][-1] = expected["expected_status"]
        if s["id"] == "dev_name_conflict":
            expected["event_states"][1] = "NEEDS_HUMAN"
        if s["id"] == "holdout_skilled_worker":
            expected["event_states"][2] = "READY_FOR_REVIEW"
            expected["before_adviser_state"] = "NEEDS_HUMAN"
        expected["max_questions"] = 3
        # Derive provenance from authored fixture text, never from a model response.
        from pypdf import PdfReader
        sources = {}
        for index, event in enumerate(s["events"]):
            for line in event["text"].splitlines():
                key, separator, value = line.partition(": ")
                if separator and expected["expected_fields"].get(key) == value:
                    sources[key] = {"event_id": f"event_{index}", "page": None}
            for name in event["attachments"]:
                path = dataset / name
                authored = path.with_suffix(".pdf") if path.suffix == ".jpg" else path
                if not authored.exists():
                    continue
                for page_index, page in enumerate(PdfReader(authored).pages, 1):
                    for line in (page.extract_text() or "").splitlines():
                        key, separator, value = line.partition(": ")
                        if separator and expected["expected_fields"].get(key) == value:
                            sources[key] = {"attachment": name, "page": page_index}
        expected["expected_sources"] = sources
        save_json(dataset / "cases" / (s["id"] + ".json"), s)
        save_json(dataset / "expected" / (s["id"] + ".json"), expected)

    # Extra module fixtures cover substitutions, translations, image variants and unsupported branches.
    extra = dataset / "materials" / "module"
    make_pdf(extra / "bank_letter.pdf", "bank_letter", {"bank_holder": "Lin Example"})
    make_pdf(extra / "travel_plan.pdf", "travel_plan", {"travel_start": "2026-11-01", "travel_end": "2026-11-15"})
    make_pdf(extra / "atas.pdf", "atas", {"atas_reference": "TEST-ATAS-001"})
    make_pdf(extra / "sponsorship.pdf", "sponsorship", {"sponsor_name": "Example Foundation"})
    make_pdf(extra / "translation.pdf", "translation", {
        "translation_for": "chinese_employment.pdf", "translator_name": "Example Translator",
        "translation_date": "2026-10-01", "translator_contact": "translator@example.invalid",
        "translation_accurate": "true", "translator_signed": "true"})
    make_pdf(extra / "chinese.pdf", "employment", {"employment_name": "测试申请人", "employer": "测试公司"}, chinese=True)
    for variant, suffix in [("scan", ".pdf"), ("photo", ".jpg"), ("rotate", ".jpg"), ("blur", ".jpg"), ("crop", ".jpg")]:
        raster(dataset / "materials" / "dev_visitor" / "identity.pdf", extra / (variant + suffix), variant)
    raster(extra / "chinese.pdf", extra / "chinese.jpg")
    # A real two-page input and a deliberately missing last page for page coverage tests.
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.append(dataset / "materials" / "dev_visitor" / "funds.pdf")
    writer.append(extra / "bank_letter.pdf")
    writer.write(extra / "two_pages.pdf")
    writer = PdfWriter()
    writer.append(extra / "two_pages.pdf", pages=(0,1))
    writer.write(extra / "missing_page.pdf")
    (extra / "corrupt.pdf").write_bytes(b"%PDF-corrupt-fixture")
    writer = PdfWriter()
    writer.append(extra / "bank_letter.pdf")
    writer.encrypt("synthetic-test-password")
    writer.write(extra / "encrypted.pdf")
    files = {str(p.relative_to(dataset)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(dataset.rglob("*")) if p.is_file() and p.name != "freeze.json"}
    save_json(dataset / "freeze.json", {"seed": 20261005, "files": files, "case_count": len(scenarios)})
    print(f"Frozen {len(scenarios)} cases and {len(files)} files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    main(parser.parse_args().force)
