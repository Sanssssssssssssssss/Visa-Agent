"""Prepare evidence figures from committed mail transcripts and an actual demo ZIP.

This writes local HTML, not a product UI. Render with Playwright; see docs/media/README.md.
"""
from html import escape
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/readme-media"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    transcript = (ROOT / "docs/full-delivery-transcripts.md").read_text(encoding="utf-8")
    stages = [
        ("01", "First contact · 首次咨询", "WAIT_USER", [
            "您好！我是签证材料助手 😊 我会帮您记好进度，一步步补齐材料。",
            "待补齐或确认：护照、资金证明、工作证明",
            "材料进度 ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0/3 项已收齐"]),
        ("02", "Send documents · 分批补件", "WAIT_USER", [
            "收到，谢谢您 😊", "✅ 已收齐：护照", "待补齐或确认：资金证明、工作证明",
            "材料进度 🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜ 1/3 项已收齐", "信息进度 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 36/36"]),
        ("03", "Receive your pack · 收到材料包", "COMPLETE · DEMO", [
            "材料收集完成！✅ 感谢您配合整理。", "✅ 已收齐：护照、资金证明、工作证明",
            "这里只确认收集完成，不代表签证获批，也未替您提交申请。",
            "📦 整理好的材料包见附件 visa-materials.zip。"]),
    ]
    cards = []
    for number, title, status, excerpts in stages:
        assert all(text in transcript for text in excerpts), "Figure must quote recorded email text"
        cards.append(f'<section><div class="number">{number}</div><h2>{title}</h2><span>{status}</span>'
                     + ''.join('<p>' + escape(text) + '</p>' for text in excerpts) + '</section>')
    html = '''<!doctype html><meta charset="utf-8"><title>Recorded email journey</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f1f5ef;color:#193d3c;font-family:"Segoe UI","Microsoft YaHei",sans-serif;padding:42px 44px;width:1440px}header{display:flex;justify-content:space-between;align-items:start;border-bottom:1px solid #c6d6cf;padding-bottom:24px;margin-bottom:28px}.kicker{font-size:13px;letter-spacing:2px;font-weight:700;color:#577770}h1{font-size:36px;margin:12px 0 8px;font-weight:650;letter-spacing:-1px}.sub{font-size:17px;color:#56716d;margin:0}.tag{padding:10px 15px;background:#dcede3;border-radius:5px;font-size:13px;font-weight:600}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}section{background:#fff;border:1px solid #d1ded7;border-radius:12px;padding:25px;min-height:420px}.number{font-size:16px;color:#69867e;font-weight:600}h2{font-size:20px;margin:16px 0}span{display:inline-block;font-size:11px;letter-spacing:.7px;background:#e9f3ed;color:#207467;padding:7px 9px;border-radius:4px}p{font-size:17px;line-height:1.8;margin:20px 0 0}footer{font-size:13px;line-height:1.8;color:#61756f;margin-top:24px;display:flex;justify-content:space-between}.brand{font-weight:700}</style>
<header><div><div class="kicker">VISA AGENT / RECORDED EMAIL DEMO</div><h1>A case that keeps moving.</h1><p class="sub">从第一封咨询，到邮件中的申请材料包。</p></div><div class="tag">Visitor · Chinese · 3 email turns</div></header><main class="grid">'''
    html += ''.join(cards) + '''</main><footer><div>Actual email excerpts, selected and typeset · 真实邮件节选排版<br>Synthetic applicant and documents · 合成申请人及材料；并非产品收件箱截图</div><div class="brand">2026-10-07<br>Outlook → QQ → model → email + ZIP</div></footer>'''
    (OUT / "email-journey.html").write_text(html, encoding="utf-8")
    pack_dir = OUT / "visitor-pack"
    with zipfile.ZipFile(ROOT / "examples/packs/visitor-demo.zip") as pack:
        for name in pack.namelist():
            assert (pack_dir / name).resolve().is_relative_to(pack_dir.resolve())
        pack.extractall(pack_dir)
    code = "async (page) => {\n"
    code += "await page.setViewportSize({width:1440,height:850});\n"
    for source, target, full in [(OUT / "email-journey.html", "email-journey.png", True),
                                  (pack_dir / "START-HERE.html", "delivery-pack.png", True)]:
        code += f"await page.goto({json.dumps(source.as_uri())});\nawait page.evaluate(() => document.fonts.ready);\n"
        code += f"await page.screenshot({{path:{json.dumps(str(ROOT / 'docs/media' / target))},fullPage:{str(full).lower()}}});\n"
    code += "return {rendered:2};\n}"
    (OUT / "capture.js").write_text(code, encoding="utf-8")
    print("Prepared output/readme-media/capture.js; render using Playwright CLI")


if __name__ == "__main__":
    main()
