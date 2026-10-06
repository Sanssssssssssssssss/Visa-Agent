"""Render published, redacted document examples exactly as visibly displayed.

Run after downloading the PDFs listed in docs/public-images.md. Rendering the
whole page preserves the publisher's visible redactions; extracting embedded
images instead could accidentally remove redaction overlays.
"""

import hashlib
import json
from pathlib import Path

import pypdfium2 as pdfium


ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    {
        "file": "02-deposit-certificate-Sussex.pdf",
        "url": "https://student.sussex.ac.uk/international/documents/certificate-deposit-example.pdf",
        "sha256": "51f83ac3429989c7d7cc70e7a3bb9cd90c23ade8a6fce69f21951eb6f0bbb98c",
        "pages": [(0, "01-BOC-deposit-redacted.png")],
    },
    {
        "file": "05-bank-statements-Bournemouth.pdf",
        "url": "https://www.bournemouth.ac.uk/sites/default/files/asset/document/TIER-4-GENERAL-BANK-STATEMENT-CHECKLIST-v11JUN2018-2.pdf",
        "sha256": "6adc190684ad8f03697ef64003eaaeae79b7a0282142eb6b5a72ae87f589e691",
        "pages": [
            (1, "02-Lloyds-statement-page1.png"),
            (2, "03-Lloyds-statement-page2.png"),
            (3, "04-Lloyds-statement-page3.png"),
        ],
    },
    {
        "file": "06-deposit-certificate-Warwick.pdf",
        "url": "https://warwick.ac.uk/study/international/visa/applying-for-a-visa/visas-for-studying/student-visa/certofdeposit.pdf",
        "sha256": "a9b209802904f34eb45131c206314ca777fd26bb5c2f2fc9102af1095099a882",
        "pages": [(0, "05-BOC-Warwick-partially-redacted.png")],
    },
]


def main() -> None:
    destination = ROOT / "external-materials" / "public-images"
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source in SOURCES:
        path = ROOT / "external-materials" / "public-samples" / source["file"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source["sha256"]:
            raise ValueError(f"Source changed: {path.name}; review before rendering")
        with pdfium.PdfDocument(path) as document:
            for page_index, filename in source["pages"]:
                page = document[page_index]
                bitmap = page.render(scale=2.5)
                try:
                    bitmap.to_pil().save(destination / filename)
                finally:
                    bitmap.close()
                    page.close()
                manifest.append({
                    "image": filename,
                    "source_url": source["url"],
                    "source_page": page_index + 1,
                    "source_sha256": digest,
                    "image_sha256": hashlib.sha256(
                        (destination / filename).read_bytes()
                    ).hexdigest(),
                    "processing": "Full visible page rendered at 180 DPI; no content edits",
                    "status": "Public redacted example; original customer authenticity unverified",
                    "redistribution": "Permission not established; local evaluation only",
                })
    (destination / "SOURCES.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (destination / "README.txt").write_text(
        "这里的 5 张图片来自大学公开 PDF 的原页渲染，不是本项目生成的虚构材料。\n"
        "01：Sussex 发布的中国银行存款证明脱敏扫描样例。\n"
        "02、03、04：Bournemouth 发布的 Lloyds 流水脱敏扫描样例，连续三页。\n"
        "05：Warwick 发布的中国银行存款证明扫描样例，姓名只露出姓氏。\n"
        "保留原有遮盖、批注、金额和日期。原始客户真实性未经独立核实。\n"
        "用法：新建空白案件，三张 Lloyds 图片一起上传；BOC 图片另建案件上传。\n"
        "可测试中文、英文、扫描读取、遮盖字段和过旧日期；这些资料不能直接用于当前签证申请。\n"
        "不要期望上传这几张图片后直接完成案件。身份等遮盖信息应保持未知或待确认。\n"
        "来源网址、页码和哈希见 SOURCES.json。仅本地测试，未确认再分发许可。\n",
        encoding="utf-8",
    )
    print(destination)
    for row in manifest:
        print(row["image"])


if __name__ == "__main__":
    main()
