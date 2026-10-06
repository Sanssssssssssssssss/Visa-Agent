"""Reproducible evidence manifest and a readable local delivery pack."""

import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile

from .rules import FINAL_REVIEW
from .store import digest, write_json
from .types import Case


def manifest(case: Case) -> dict:
    return {
        "case_id": case.id, "version": case.version, "route": case.route,
        "rule_version": case.rule_version,
        "test_mode": case.test_mode,
        "documents": [{"id": d.id, "name": d.name, "sha256": d.sha256, "kind": d.kind,
                       "language": d.language, "content_role": d.content_role} for d in case.documents if not d.rejected],
        "facts": [f.model_dump() for f in case.facts if f.active],
        "checks": [c.model_dump() for c in case.checks],
    }


def build_pack(case: Case, root: Path) -> str:
    content = manifest(case)
    directory = root / "packs" / case.id / f"v{case.version}-{digest(content)[:12]}"
    originals = directory / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    for doc in case.documents:
        if doc.rejected:
            continue
        source = Path(doc.path)
        if hashlib.sha256(source.read_bytes()).hexdigest() != doc.sha256:
            raise ValueError(f"Stored evidence was modified: {doc.id}")
        shutil.copyfile(source, originals / (doc.id + source.suffix))
    write_json(directory / "manifest.json", content)
    write_json(directory / "review.json", {"approval": case.approval.model_dump() if case.approval else None,
                                            "review_history": case.reviews})
    def esc(value):
        return html.escape(str(value))
    rows = "".join(f"<tr><td>{esc(c.id)}</td><td>{esc(c.status)}</td><td>{esc(c.message)}</td>"
                   f"<td>{esc(c.source)}</td></tr>" for c in case.checks)
    facts = "".join(f"<tr><td>{esc(f.key)}</td><td>{esc(f.value)}</td>"
                    f"<td>{esc(f.source_id)} / {esc(f.page)}</td><td>{esc(f.quote)}</td></tr>"
                    for f in case.facts if f.active)
    docs = "".join(f'<li><a href="originals/{d.id}{Path(d.path).suffix}">{esc(d.name)}</a>'
                   f" — {esc(d.sha256)}</li>" for d in case.documents if not d.rejected)
    review = "".join(f"<li>{esc(item)}</li>" for item in FINAL_REVIEW)
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
<p>本报告记录材料准备检查与人工复核，不代表签证获批。真实性、资格及适用条件须由顾问核对。</p>
<p>规则版本：{esc(case.rule_version)}<br>证据清单哈希：{digest(content)}</p>
<h2>原始材料</h2><ul>{docs}</ul><h2>检查结果</h2>
<table class="checks"><tr><th>检查</th><th>结果</th><th>说明</th><th>依据</th></tr>{rows}</table>
<h2>事实与来源</h2><table><tr><th>字段</th><th>值</th><th>来源/页码</th><th>原文</th></tr>{facts}</table>
<h2>顾问复核清单</h2><ul>{review}</ul>
<h2>审批</h2><pre>{esc(case.approval.model_dump_json(indent=2) if case.approval else '等待当前版本人工确认')}</pre>
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
        expected = {"manifest.json", "review.json", "report.html"}
        for doc in case.documents:
            if not doc.rejected:
                name = f"originals/{doc.id}{Path(doc.path).suffix}"
                expected.add(name)
                if hashlib.sha256(archive.read(name)).hexdigest() != doc.sha256:
                    raise ValueError("Review pack evidence was modified")
        if set(archive.namelist()) != expected:
            raise ValueError("Review pack contains unexpected or missing files")
