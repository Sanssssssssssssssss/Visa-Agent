"""Regression: captions must never hide the raster evidence next to them."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pytest
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from visa_agent.documents import read_document


@pytest.fixture
def mixed_pdf(tmp_path):
    image = Image.new("RGB", (1200, 450), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=38)
    draw.text((30, 40), "BANK CERTIFICATE", fill="black", font=font)
    draw.text((30, 115), "Balance: GBP 32456.78", fill="black", font=font)
    draw.text((30, 190), "Issued: 2026-09-30", fill="black", font=font)
    path = tmp_path / "mixed.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(40, 780, "Supporting document guidance: please read the certificate shown below.")
    # Put the image in a Form XObject as well, as many exported PDFs do.
    pdf.beginForm("certificate")
    pdf.drawImage(ImageReader(image), 40, 480, width=500, height=187.5)
    pdf.endForm()
    pdf.doForm("certificate")
    pdf.save()
    image.close()
    return path


def test_image_body_is_read_despite_long_text_layer(mixed_pdf):
    from pypdf import PdfReader
    text_layer = PdfReader(mixed_pdf).pages[0].extract_text()
    assert len(text_layer) > 40 and "32456" not in text_layer
    doc = read_document(mixed_pdf, "1" * 64, mixed_pdf.name)
    assert doc.pages[0].method == "ocr"
    assert "32456.78" in doc.pages[0].text and "2026-09-30" in doc.pages[0].text
    assert "Supporting document guidance" in doc.pages[0].text


def test_ocr_failure_is_not_silently_replaced_by_caption(mixed_pdf, monkeypatch):
    def broken(*args):
        raise RuntimeError("OCR unavailable")
    monkeypatch.setattr("visa_agent.documents.image_text", broken)
    doc = read_document(mixed_pdf, "1" * 64, mixed_pdf.name)
    assert not doc.pages and any("OCR unavailable" in p for p in doc.problems)


def test_pure_text_still_avoids_ocr(monkeypatch):
    def unexpected(*args):
        pytest.fail("Text-only PDF should not need OCR")
    monkeypatch.setattr("visa_agent.documents.image_text", unexpected)
    path = Path(__file__).resolve().parents[1] / "datasets/materials/dev_visitor/identity.pdf"
    doc = read_document(path, "2" * 64, path.name)
    assert doc.pages[0].method == "pdf_text" and "Lin Example" in doc.pages[0].text
