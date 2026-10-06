"""Reproducible evidence manifest and a readable local delivery pack."""

import hashlib
import html
import json
from pathlib import Path
import re
import shutil
from urllib.parse import quote
import zipfile

from .rules import FINAL_REVIEW
from .store import digest, write_json
from .submission import bilingual_guide
from .types import Case


def archive_path(doc) -> str:
    """Keep readable names, isolate intake forms, and prevent collisions/traversal."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", doc.name).strip(" .")[:100] or "document"
    folder = "information/source-forms" if doc.kind == "intake" else "documents"
    return f"{folder}/{doc.id}-{name}"


def start_page(case: Case) -> str:
    esc = html.escape
    documents = "".join(
        f'<li><a href="{quote(archive_path(d))}">{esc(d.name)}</a> — {esc(d.kind)}</li>'
        for d in case.documents if not d.rejected and d.kind != "intake")
    worksheet = ('<p><a href="application-information.xlsx">填好的信息表 / Completed worksheet</a></p>'
                 if case.application_forms else "")
    warning = ('<p class="notice">演示材料 · 仅供测试，不能用于真实申请。<br>DEMO ONLY — not valid application evidence.</p>'
               if case.test_mode else "")
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>您的签证材料 / Your visa documents</title><style>
body{{max-width:850px;margin:40px auto;padding:0 24px;font:17px/1.7 system-ui;color:#20313d}}
h1,h2{{color:#155e63}}a{{color:#156677}}.notice{{background:#fff4dd;padding:16px}}
li{{margin:8px 0;overflow-wrap:anywhere}}</style>
<h1>您的材料已整理好 ✅<br>Your documents are organised</h1>{warning}
<p>{esc(case.route.value if case.route else '')} · {esc(case.id)} · v{case.version}</p>
<p>请先核对自己的信息。收齐本版清单不等于满足全部签证资格，也不表示已经提交或获批。<br>
Please check your details. Completing this checklist does not establish full visa eligibility, submission or approval.</p>
<h2>1. 信息 / Your information</h2>{worksheet}
<p>信息表用于准备官网答案；历史回传表在 information/source-forms。<br>
The worksheet helps you complete the official application. Earlier returned forms are in information/source-forms.</p>
<h2>2. 原始材料 / Original documents</h2><ul>{documents}</ul>
<p>文件内容保持原样。按官方清单选择上传，勿把整份 ZIP 当作证据提交。<br>
Original bytes are preserved. Select files requested by the official checklist; do not upload this whole ZIP as evidence.</p>
<h2>3. 提交与预约 / Apply and arrange identity checks</h2>
<p><a href="submission-guide.txt">中英双语申请与预约步骤 / Bilingual application and appointment guide</a></p>
<details><summary>检查记录 / Checking records</summary><p><a href="report.html">检查报告 / Report</a> ·
<a href="manifest.json">文件与来源 / Manifest</a> · <a href="review.json">交付记录 / Delivery record</a></p>
<p>这些是本服务的记录，不是官方证明。 / These are service records, not official evidence.</p></details></html>'''


def manifest(case: Case) -> dict:
    return {
        "case_id": case.id, "version": case.version, "route": case.route,
        "rule_version": case.rule_version,
        "test_mode": case.test_mode,
        "hitl_enabled": case.hitl_enabled,
        "application_forms": case.application_forms,
        "documents": [{"id": d.id, "name": d.name, "sha256": d.sha256, "kind": d.kind,
                       "language": d.language, "content_role": d.content_role,
                       "archive_path": archive_path(d)} for d in case.documents if not d.rejected],
        "facts": [f.model_dump() for f in case.facts if f.active],
        "checks": [c.model_dump() for c in case.checks],
    }


def build_pack(case: Case, root: Path) -> str:
    content = manifest(case)
    directory = root / "packs" / case.id / f"v{case.version}-{digest(content)[:12]}"
    directory.mkdir(parents=True, exist_ok=True)
    for doc in case.documents:
        if doc.rejected:
            continue
        source = Path(doc.path)
        if hashlib.sha256(source.read_bytes()).hexdigest() != doc.sha256:
            raise ValueError(f"Stored evidence was modified: {doc.id}")
        target = directory / archive_path(doc)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    write_json(directory / "manifest.json", content)
    (directory / "START-HERE.html").write_text(start_page(case), encoding="utf-8", newline="\n")
    (directory / "submission-guide.txt").write_text(bilingual_guide(case.route), encoding="utf-8", newline="\n")
    if case.application_forms:
        from .intake import write_form
        write_form(case, directory / "application-information.xlsx")
    write_json(directory / "review.json", {"approval": case.approval.model_dump() if case.approval else None,
                                            "automatic_completion": case.automatic_completion.model_dump() if case.automatic_completion else None,
                                            "review_history": case.reviews})
    def esc(value):
        return html.escape(str(value))
    rows = "".join(f"<tr><td>{esc(c.id)}</td><td>{esc(c.status)}</td><td>{esc(c.message)}</td>"
                   f"<td>{esc(c.source)}</td></tr>" for c in case.checks)
    facts = "".join(f"<tr><td>{esc(f.key)}</td><td>{esc(f.value)}</td>"
                    f"<td>{esc(f.source_id)} / {esc(f.page)}</td><td>{esc(f.quote)}</td></tr>"
                    for f in case.facts if f.active)
    docs = "".join(f'<li><a href="{quote(archive_path(d))}">{esc(d.name)}</a>'
                   f" — {esc(d.sha256)}</li>" for d in case.documents if not d.rejected)
    review = "".join(f"<li>{esc(item)}</li>" for item in FINAL_REVIEW)
    outcome = (case.approval.model_dump_json(indent=2) if case.approval else
               "材料收集完成（未经人工审核）\n" + case.automatic_completion.model_dump_json(indent=2) if case.automatic_completion else
               "等待当前版本人工确认" if case.hitl_enabled else "尚未自动完成；HITL 已关闭")
    report = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>材料包 {esc(case.id)}</title><style>
body{{max-width:1100px;margin:40px auto;padding:0 24px;font:16px/1.6 system-ui;color:#182b38}}
h1,h2{{color:#155e63}}table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{padding:8px;border:1px solid #ccd7dc;text-align:left;overflow-wrap:anywhere}}
.checks{{table-layout:fixed}}.checks th:nth-child(1){{width:18%}}
.checks th:nth-child(2){{width:9%}}.checks th:nth-child(3){{width:40%}}
.checks th:nth-child(4){{width:33%}}.checks td:nth-child(2){{white-space:nowrap}}
.status{{padding:14px;background:#edf5f4}}li{{overflow-wrap:anywhere}}
</style><h1>{'演示材料包 · 仅供测试' if case.test_mode else '申请材料准备报告'}</h1><p class="status">案件 {esc(case.id)} · 版本 {case.version}
· {esc(case.status)} · {esc(case.route)}</p>
<p>本报告记录材料准备检查及本案交付方式，不代表签证获批，不进行材料真伪鉴定。自动完成不包含人工审核。</p>
<p>规则版本：{esc(case.rule_version)}<br>证据清单哈希：{digest(content)}</p>
<h2>原始材料</h2><ul>{docs}</ul><h2>检查结果</h2>
<table class="checks"><tr><th>检查</th><th>结果</th><th>说明</th><th>依据</th></tr>{rows}</table>
<h2>事实与来源</h2><table><tr><th>字段</th><th>值</th><th>来源/页码</th><th>原文</th></tr>{facts}</table>
<h2>{'顾问复核清单' if case.hitl_enabled else '收集范围之外的事项'}</h2><ul>{review}</ul>
<h2>交付记录</h2><pre>{esc(outcome)}</pre>
</html>"""
    (directory / "report.html").write_text(report, encoding="utf-8")
    archive = directory.with_suffix(".zip")
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(directory.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(directory))
    temporary.replace(archive)
    return str(archive)


def verify_pack(case: Case) -> None:
    """Verify the pack the adviser reviewed before binding an approval to it."""
    with zipfile.ZipFile(case.pack_path) as archive:
        if digest(json.loads(archive.read("manifest.json"))) != digest(manifest(case)):
            raise ValueError("Review pack manifest was modified")
        expected = {"manifest.json", "review.json", "report.html", "START-HERE.html", "submission-guide.txt"}
        if (archive.read("START-HERE.html").decode("utf-8") != start_page(case)
                or archive.read("submission-guide.txt").decode("utf-8") != bilingual_guide(case.route)):
            raise ValueError("Pack handover guide was modified")
        if case.application_forms:
            expected.add("application-information.xlsx")
            from .intake import read_rows
            from .intake_schema import VERSION, questions
            from .evidence import Evidence
            from io import BytesIO
            meta, rows = read_rows(BytesIO(archive.read("application-information.xlsx")))
            e = Evidence(case)
            if (meta.get("case_id") != case.id or meta.get("route") != case.route or meta.get("version") != VERSION
                    or [key for key, _, _ in rows] != [q.key for q in questions(case.route)]
                    or any(value != (e.get(key) or "") for key, value, _ in rows)):
                raise ValueError("Pack information worksheet was modified")
        for doc in case.documents:
            if not doc.rejected:
                name = archive_path(doc)
                expected.add(name)
                if hashlib.sha256(archive.read(name)).hexdigest() != doc.sha256:
                    raise ValueError("Review pack evidence was modified")
        if set(archive.namelist()) != expected:
            raise ValueError("Review pack contains unexpected or missing files")
