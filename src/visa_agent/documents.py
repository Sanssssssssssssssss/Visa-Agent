"""Read real bytes. OCR failure is explicit; no fixture text or mock fallback."""

import ctypes
from functools import lru_cache
import hashlib
from pathlib import Path
import re
import shutil

from PIL import Image
from pypdf import PdfReader
import pypdfium2 as pdfium

from .types import Document, Page

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 20
Image.MAX_IMAGE_PIXELS = 25_000_000


def needs_visible_page_ocr(page) -> bool:
    """Images or filled vector shapes may conceal/replace text-layer content."""
    for obj in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE, pdfium.raw.FPDF_PAGEOBJ_PATH]):
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            return True
        fill, stroke = ctypes.c_int(), ctypes.c_int()
        if not pdfium.raw.FPDFPath_GetDrawMode(obj, fill, stroke):
            raise ValueError("Cannot inspect PDF drawing mode")
        if fill.value != pdfium.raw.FPDF_FILLMODE_NONE:
            return True
    return False


@lru_cache(maxsize=1)
def ocr_engine():
    from rapidocr import RapidOCR
    # Default models support Chinese + English. Downloads are a setup dependency.
    return RapidOCR(params={"EngineConfig.onnxruntime.intra_op_num_threads": 2,
                            "EngineConfig.onnxruntime.inter_op_num_threads": 2})


def image_text(image: Image.Image, page: int) -> Page:
    import numpy as np
    result = ocr_engine()(np.array(image.convert("RGB")))
    texts = list(result.txts) if result.txts is not None else []
    scores = list(result.scores) if result.scores is not None else []
    return Page(number=page, text="\n".join(texts), method="ocr",
                confidence=float(min(scores)) if scores else 0.0)


def pagination_problems(pages: list[Page]) -> list[str]:
    """Check one uploaded document; unrelated image files cannot prove completeness."""
    declared = {}
    for page in pages:
        for number, total in re.findall(r"^\s*Page\s+(\d+)\s*(?:of|/)\s*(\d+)\s*$",
                                        page.text, re.I | re.M):
            declared.setdefault(int(total), set()).add(int(number))
    return [f"Declared pagination incomplete: missing pages (received {sorted(seen)} of {total})"
            for total, seen in declared.items()
            if total > MAX_PAGES or (total > 0 and seen != set(range(1, total + 1)))]


def stage_file(source: str | Path, root: Path) -> tuple[str, Path]:
    source = Path(source).resolve(strict=True)
    if source.stat().st_size > MAX_BYTES:
        raise ValueError("File exceeds 10 MB; split it before uploading")
    suffix = source.suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg"}:
        raise ValueError("Only PDF, PNG and JPEG files are supported")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    dest = root / "files" / f"{sha}{suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        temporary = dest.with_suffix(dest.suffix + ".tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(dest)
    return sha, dest


def read_document(path: Path, sha: str, original_name: str) -> Document:
    doc = Document(id=sha[:20], sha256=sha, path=str(path), name=original_name)
    try:
        if path.suffix == ".pdf":
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDF: upload an unlocked copy")
            if not 1 <= len(reader.pages) <= MAX_PAGES:
                raise ValueError("PDF must contain 1-20 pages")
            with pdfium.PdfDocument(path) as rendered:
                for index, source in enumerate(reader.pages):
                    text = source.extract_text() or ""
                    pdf_page = rendered[index]
                    try:
                        # A long text layer can be only captions beside a scanned document.
                        # Filled vector boxes can hide personal data even without images.
                        if not needs_visible_page_ocr(pdf_page) and len(text.strip()) >= 40 and text.count("\ufffd") < 3:
                            page = Page(number=index + 1, text=text, method="pdf_text")
                        else:
                            width, height = pdf_page.get_size()
                            if width * height * 4 > Image.MAX_IMAGE_PIXELS:
                                raise ValueError("PDF page exceeds rendering pixel limit")
                            bitmap = pdf_page.render(scale=2)
                            try:
                                with bitmap.to_pil() as pixels:
                                    page = image_text(pixels, index + 1)
                            finally:
                                bitmap.close()
                    finally:
                        pdf_page.close()
                    doc.pages.append(page)
        else:
            with Image.open(path) as im:
                if im.width * im.height > Image.MAX_IMAGE_PIXELS:
                    raise ValueError("Image exceeds pixel limit")
                doc.pages.append(image_text(im, 1))
        doc.problems.extend(pagination_problems(doc.pages))
        for page in doc.pages:
            if len(page.text.strip()) < 20:
                doc.problems.append(f"page {page.number}: unreadable")
            if page.confidence is not None and page.confidence < 0.8:
                doc.problems.append(f"page {page.number}: low OCR confidence")
    except Exception as exc:
        doc.problems.append(f"{type(exc).__name__}: {exc}")
    return doc
