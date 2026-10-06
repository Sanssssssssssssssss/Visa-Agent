"""Create readable fictional document layouts and raster scans for demo-only tests.

No real issuer logos, signatures, seals, security features or personal photos.
The visible test label is retained in every rendered file.
"""
import argparse
import hashlib
import json
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "datasets/formatted-materials"


def render(path, title, rows):
    pdf = canvas.Canvas(str(path), pagesize=(595, 842), invariant=1)
    pdf.setFillColor(HexColor("#155e63"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(42, 784, title)
    pdf.setFillColor(HexColor("#9b4d00"))
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(42, 755, "TEST SPECIMEN - NOT VALID FOR APPLICATION")
    pdf.setStrokeColor(HexColor("#155e63"))
    pdf.line(42, 735, 552, 735)
    y = 695
    for label, value in rows:
        pdf.setFillColor(HexColor("#53636d"))
        pdf.setFont("Helvetica", 11)
        pdf.drawString(42, y, label)
        pdf.setFillColor(HexColor("#162c36"))
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(42, y-21, str(value))
        y -= 57
    pdf.setFillColor(HexColor("#53636d"))
    pdf.setFont("Helvetica", 10)
    pdf.drawString(42, 62, "Fictional layout for software testing. No issuer authentication.")
    pdf.drawString(42, 45, "Page 1 of 1")
    pdf.save()
    with pdfium.PdfDocument(path) as document:
        page = document[0]
        bitmap = page.render(scale=2)
        with bitmap.to_pil() as image:
            image.convert("RGB").save(path.with_suffix(".jpg"), quality=94)
            image.convert("RGB").save(path.with_name(path.stem+"-scan.pdf"), "PDF", resolution=144)
        bitmap.close()
        page.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output
    if (output / "manifest.json").exists():
        raise ValueError("Samples already frozen; do not overwrite prior experiment inputs")
    for route in ("visitor", "student", "skilled_worker"):
        answers = json.loads((ROOT / f"datasets/intake/{route}-answers.json").read_text(encoding="utf-8"))
        directory = output / route
        directory.mkdir(parents=True, exist_ok=True)
        name = answers["applicant_name"]
        render(directory / "identity.pdf", "Passport details - demonstration", [
            ("Full name", name), ("Nationality", "China"),
            ("Passport number", answers["passport_number"]), ("Date of expiry", answers["passport_expiry"])])
        if route != "skilled_worker":
            render(directory / "funds.pdf", "Fictional Example Bank | Statement", [
                ("Account holder", name), ("Currency", "GBP"), ("Statement period starts", "2026-08-01"),
                ("Statement period ends", "2026-09-28"), ("Minimum balance throughout the period", "GBP 40000"),
                ("Opening balance / closing balance", "GBP 40000 / GBP 40000"),
                ("Transactions during this period", "None")])
        if route == "visitor":
            render(directory / "work.pdf", "Employment confirmation", [
                ("Employer", answers["employer"]), ("Employee", name),
                ("Employment status", "Employed"), ("Role", "Designer"),
                ("Employer address and phone", answers["employer_contact"]), ("Issued", "2026-09-28")])
        if route == "student":
            render(directory / "school.pdf", "Confirmation of Acceptance for Studies", [
                ("Student name", name), ("CAS reference", answers["cas_reference"]),
                ("Tuition remaining to pay", "GBP 16000"), ("Course length in months", "12"),
                ("Study location", "outside London"), ("English requirement confirmed", "Yes"),
                ("ATAS required", "No")])
        if route == "skilled_worker":
            render(directory / "sponsor.pdf", "Certificate of Sponsorship - details", [
                ("Worker name", name), ("CoS reference", answers["cos_reference"]),
                ("Sponsor", answers["sponsor_name"]), ("Sponsor licence number", answers["sponsor_licence"]),
                ("Job title", answers["job_title"]), ("Occupation code", answers["occupation_code"]),
                ("Annual salary", "GBP 65000"), ("Sponsor certifies maintenance", "Yes")])
            render(directory / "language.pdf", "English language test - demonstration", [
                ("Candidate", name), ("CEFR English level", "B2"),
                ("Skills covered", "Reading, writing, speaking and listening")])
        if route != "visitor":
            render(directory / "health.pdf", "TB screening - demonstration", [
                ("Applicant name", name), ("TB clear", "Yes"),
                ("Certificate expires", "2027-02-01")])
    manifest = {"synthetic":True,"purpose":"Layout/OCR and demo progression, not proof of authenticity or genuine passport validation",
        "files":{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(output.rglob('*')) if p.is_file()}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(f"Generated {len(manifest['files'])} labelled layout / image / scan inputs")


if __name__ == "__main__":
    main()
