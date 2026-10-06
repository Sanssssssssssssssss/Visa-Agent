"""Interactive local QQ setup. The authorization code is never echoed or logged."""
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

from msal_extensions import build_encrypted_persistence

from visa_agent.inbox import normalize_sender
from visa_agent.store import write_json

ROOT = Path(__file__).resolve().parents[1] / "data/qq-test"


def main():
    print("Visa Agent · QQ 邮箱本机配置\n授权码只在此窗口输入，不要发到聊天里。\n")
    mailbox = normalize_sender("email", input("Agent 收件 QQ 邮箱地址：").strip())
    if mailbox.split("@")[-1] not in {"qq.com", "foxmail.com"}:
        raise ValueError("请输入 QQ 或 Foxmail 邮箱")
    sender_input = input("允许的客户发件邮箱（留空则接受所有发件人）：").strip()
    sender = normalize_sender("email", sender_input) if sender_input else None
    if sender == mailbox:
        raise ValueError("客户发件邮箱应与 Agent 邮箱不同")
    code = getpass("QQ 邮箱 16 位授权码（不显示）：").replace(" ", "").strip()
    if len(code) != 16 or not code.isascii() or not code.isalpha():
        raise ValueError("请输入 QQ 邮箱生成的 16 位字母授权码")
    ROOT.mkdir(parents=True, exist_ok=True)
    persistence = build_encrypted_persistence(str(ROOT / "qq-auth.bin"))
    persistence.save(code)
    write_json(ROOT / "qq-config.json", {"mailbox": mailbox, "allowed_senders": [sender] if sender else [],
                "accept_all": sender is None, "require_tag": False,
                "since": datetime.now(timezone.utc).isoformat(), "hitl": False})
    print("\n配置已保存（Windows DPAPI 加密）。这一步还未收发邮件。\n请回到 Codex 告诉我：QQ 配置好了。")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not print credential-bearing provider errors.
        print("配置未保存完成：" + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
    input("\n按回车关闭此窗口。")
