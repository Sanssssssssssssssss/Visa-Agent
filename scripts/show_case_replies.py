"""Export exact customer replies and observable model responses for local review."""

import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "lloyds-complete-images": "Lloyds 三张图片一起上传",
    "lloyds-split-images": "Lloyds 分批补页",
    "lloyds-missing-middle": "Lloyds 缺少中间页",
    "sussex-deposit-image": "Sussex 存款证明图片",
    "warwick-partial-name": "Warwick 姓名部分遮盖",
    "warwick-pressure": "Warwick 诱导改姓名、币种及批准",
    "warwick-original-pdf": "Warwick 原始 PDF",
    "mixed-financial-sources": "不同资金材料混传",
}


def communication_checks(reply, trace):
    """Frozen mechanical checks; do not label these as adviser quality scores."""
    failures = []
    if trace.get("input", {}).get("attachments") and not any(
        word in reply for word in ("收到", "已读取", "已整理", "received")
    ):
        failures.append("没有确认收到材料")
    blockers = [c for c in trace.get("after", {}).get("checks", [])
                if c["status"] in {"fail", "unknown"}]
    document_issue = any(c["id"].startswith(("read:", "context:", "pagination:", "translation:", "kind:"))
                         for c in blockers)
    if document_issue and not any(word in reply.lower() for word in ("页面", "读取", "译", "阅读", "扫描", "是什么证明", "read", "pages", "translation", "identify", "sample", "样例")):
        failures.append("没有解释材料问题")
    if reply.count("合成 PDF") + reply.count("合并为 PDF") > 1:
        failures.append("重复要求合并同一组页面")
    if len(re.findall(r"^\d+\. ", reply, re.M)) > 3:
        failures.append("超过三个行动项")
    return failures


def esc(value):
    return html.escape(str(value), quote=True)


def pretty(value):
    return esc(json.dumps(value, ensure_ascii=False, indent=2))


def build(batch_paths, destination):
    destination.mkdir(parents=True, exist_ok=True)
    assets = destination / "assets"
    assets.mkdir(exist_ok=True)
    materials, cards, records = {}, [], []
    for batch in batch_paths:
        for path in sorted((batch / "runs").glob("*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            traces = json.loads((batch / "traces" / path.name).read_text(encoding="utf-8"))
            traces_by_id = {t["run_id"]: t for t in traces}
            turns = []
            for number, result in enumerate(row["results"], 1):
                trace = traces_by_id.get(result["run_id"], {})
                incoming = trace.get("input", {})
                links = []
                for filename in incoming.get("attachments", []):
                    source = Path(filename).resolve()
                    if not source.is_relative_to(ROOT) or not source.is_file():
                        continue
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                    asset = digest[:12] + "-" + source.name
                    shutil.copyfile(source, assets / asset)
                    materials[asset] = source.name
                    links.append(f'<a href="assets/{esc(asset)}" target="_blank">{esc(source.name)}</a>')
                messages = [m for m in trace.get("messages", []) if m.get("kind") == "response"]
                if not messages:
                    messages = [r for r in trace.get("http_responses", []) if r.get("messages")]
                issues = communication_checks(result["reply"], trace)
                record = {
                    "batch": batch.name, "id": row["id"], "turn": number,
                    "input": incoming, "customer_reply": result["reply"],
                    "model_responses": messages, "model_proposal": trace.get("proposal"),
                    "model_guidance": trace.get("guidance"), "context_policy": trace.get("context_policy"),
                    "rejected_candidates": trace.get("rejected_candidates", []),
                    "tools": trace.get("tools", []), "error": result.get("error"),
                    "status": result["status"], "guardrail_pass": row["passed"],
                    "communication_failures": issues, "usage": trace.get("usage", {}),
                    "diagnostics": trace.get("diagnostics", []), "visual_inputs": trace.get("visual_inputs", []),
                    "material_progress": trace.get("material_progress"),
                }
                records.append(record)
                fields = "".join(
                    f'<tr><td>{esc(f["key"])}</td><td>{esc(f["value"])}</td><td>{esc(f["confidence"])}</td>'
                    f'<td>{esc(f["source_id"])} / 页 {esc(f.get("page"))}</td><td>{esc(f["quote"])}</td></tr>'
                    for f in (trace.get("proposal") or {}).get("facts", [])
                )
                checks = "；".join(issues) if issues else "四项机械回复检查满足；顾问质量仍需人工判断"
                missing = "" if messages else "<p>本次没有保留完整模型响应，不能从最终状态反推模型原话。</p>"
                turns.append(f'''<section><h3>第 {number} 轮 · {esc(result['status'])}</h3>
                    <p>{' · '.join(links) or '本轮没有新附件'}</p>
                    <details><summary>客户输入原文</summary><pre>{esc(incoming.get('text', ''))}</pre></details>
                    <h4>客户实际看到的回复（由规则代码生成）</h4><pre class="reply">{esc(result['reply'])}</pre>
                    <p class="{'issue' if issues else 'muted'}">{esc(checks)}</p>
                    <details><summary>模型候选字段及原文引用（尚未等于校验通过）</summary><div class="scroll">
                    <table><tr><th>字段</th><th>值</th><th>置信度</th><th>来源</th><th>引用原文</th></tr>{fields}</table></div></details>
                    <details><summary>每次模型响应原文：工具调用 / final_result JSON</summary>{missing}<pre>{pretty(messages)}</pre></details>
                    <details><summary>应用拒绝项、工具结果、错误、用量</summary><pre>{pretty({k: record[k] for k in ('rejected_candidates', 'tools', 'error', 'usage')})}</pre></details>
                    <details><summary>问题分类、原图发送记录、材料进度</summary><pre>{pretty({k: record[k] for k in ('diagnostics', 'visual_inputs', 'material_progress')})}</pre></details>
                    </section>''')
            search = f"{batch.name} {row['id']} {LABELS.get(row['scenario'], '')}"
            cards.append(f'''<article data-search="{esc(search.lower())}">
                <h2>{esc(LABELS.get(row['scenario'], row['scenario']))}</h2>
                <p class="muted">{esc(batch.name)} / {esc(row['id'])} · 场景预期：{'满足' if row['passed'] else '不满足'} · 请求 {row['usage']['requests']}</p>
                {''.join(turns)}</article>''')
    gallery = []
    for asset, name in materials.items():
        image = f'<img loading="lazy" src="assets/{esc(asset)}" alt="{esc(name)}">' if Path(asset).suffix.lower() != ".pdf" else '<div class="pdf">PDF 原文件</div>'
        gallery.append(f'<a href="assets/{esc(asset)}" target="_blank">{image}<span>{esc(name)}</span></a>')
    issues = sum(bool(r["communication_failures"]) for r in records)
    document = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Visa Agent · 材料与逐轮回复</title><link rel="icon" href="data:,"><style>
        body{font:16px/1.6 "Segoe UI","Microsoft YaHei",sans-serif;background:#f2f5f7;color:#203248;margin:0}
        main{max-width:1180px;margin:30px auto;padding:0 22px}h1{font-size:30px}h2{font-size:22px}
        article,header{background:white;padding:24px;margin:20px 0;border:1px solid #dae1e8;border-radius:10px}
        section{border-top:1px solid #ddd;padding:14px 0}.muted{color:#627084}.issue{color:#ad3820}
        pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px;font-size:14px}.reply{background:#e9f3ff}
        details{margin:12px 0}summary{cursor:pointer;font-weight:600}.scroll{overflow:auto}
        table{border-collapse:collapse;font-size:13px;width:100%}td,th{border:1px solid #d6dde5;padding:8px;text-align:left;white-space:pre-wrap}
        input{box-sizing:border-box;width:100%;padding:14px;font:inherit;border:1px solid #aab8c8;border-radius:6px}
        .gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px}.gallery img,.pdf{height:230px;width:100%;object-fit:contain;background:#e9eef3}.gallery span{display:block;font-size:13px}a{color:#1f5c9e}.pdf{display:grid;place-items:center}
        </style><main><header><h1>材料与逐轮回复</h1>
        <p>材料包含公开脱敏样例及明确标记的测试文件，不能当作已核验的客户材料。点击可查看原文件；客户回复逐字来自运行记录。新版本由模型提取事实并在检查后选择下一轮引导，应用组织核对结果、风险说明与进度。历史回复保持原样。</p>
        <p>COUNT</p><details><summary>检查原始材料</summary><div class="gallery">GALLERY</div></details>
        <input id="search" placeholder="筛选场景或阶段，例如 Warwick、before、after、split"><p id="visible" class="muted"></p></header>
        CARDS</main><script>const s=document.getElementById('search');function filter(){let n=0;for(const a of document.querySelectorAll('article')){a.hidden=!a.dataset.search.includes(s.value.toLowerCase());if(!a.hidden)n++}document.getElementById('visible').textContent='显示 '+n+' 次案件运行'}s.addEventListener('input',filter);filter();</script></html>'''
    document = document.replace("COUNT", f"{len(cards)} 次案件运行，{len(records)} 轮客户回复；{issues} 轮未满足机械回复检查。完整原文在每轮的展开项中。")
    document = document.replace("GALLERY", "".join(gallery)).replace("CARDS", "".join(cards))
    (destination / "index.html").write_text(document, encoding="utf-8")
    (destination / "replies.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(destination / "index.html"), "runs": len(cards),
                      "turns": len(records), "communication_failures": issues}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batches", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "output/reply-review")
    args = parser.parse_args()
    build(args.batches, args.output.resolve())
