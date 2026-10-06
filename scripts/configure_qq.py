"""Interactive local QQ setup. The authorization code is never echoed or logged."""
import argparse
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
import os

from msal_extensions import build_encrypted_persistence

from visa_agent.inbox import normalize_sender
from visa_agent.store import write_json
from visa_agent.config import load_environment

ROOT = Path(__file__).resolve().parents[1] / "data/qq-test"


def main():
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT)
    parser.add_argument("--from-env", action="store_true", help="Read VISA_QQ_MAILBOX/AUTH_CODE/ALLOWED_SENDERS; store no credential")
    parser.add_argument("--accept-all", action=argparse.BooleanOptionalAction,
                        default=None, help="With --from-env, allow any sender (default); --no-accept-all restricts intake")
    parser.add_argument("--allow-samples", action=argparse.BooleanOptionalAction,
                        default=os.getenv("VISA_QQ_ALLOW_SAMPLES", "0") == "1", help="Enable synthetic demo documents for new cases")
    args = parser.parse_args()
    if (args.data / "qq-config.json").exists():
        raise ValueError("Configuration already exists. Edit it locally; setup will not reset the intake timestamp or sender policy.")
    if args.from_env:
        mailbox = normalize_sender("email", os.environ["VISA_QQ_MAILBOX"])
        senders = [normalize_sender("email", s.strip()) for s in os.getenv("VISA_QQ_ALLOWED_SENDERS", "").split(",") if s.strip()]
        code = os.environ["VISA_QQ_AUTH_CODE"]
        accept_all = args.accept_all if args.accept_all is not None else os.getenv("VISA_QQ_ACCEPT_ALL", "1") == "1"
        if not accept_all and not senders:
            raise ValueError("Set VISA_QQ_ALLOWED_SENDERS or explicitly choose --accept-all")
    else:
        if args.accept_all is not None:
            parser.error("--accept-all is used with --from-env; interactive setup asks for sender policy")
        print("Visa Agent · QQ 邮箱本机配置 / local mailbox setup\n")
        mailbox = normalize_sender("email", input("Agent QQ/Foxmail address / 收件邮箱：").strip())
        sender_input = input("Allowed customer address / 允许的发件邮箱（blank = all / 留空开放收件）：").strip()
        senders = [normalize_sender("email", sender_input)] if sender_input else []
        accept_all = not senders
        code = getpass("QQ 16-letter authorization code / 授权码（hidden / 不显示）：").replace(" ", "").strip()
    if mailbox.split("@")[-1] not in {"qq.com", "foxmail.com"}:
        raise ValueError("请输入 QQ 或 Foxmail 邮箱")
    if mailbox in senders:
        raise ValueError("客户发件邮箱应与 Agent 邮箱不同")
    if len(code) != 16 or not code.isascii() or not code.isalpha():
        raise ValueError("请输入 QQ 邮箱生成的 16 位字母授权码")
    args.data.mkdir(parents=True, exist_ok=True)
    if not args.from_env:
        build_encrypted_persistence(str(args.data / "qq-auth.bin")).save(code)
    write_json(args.data / "qq-config.json", {"mailbox": mailbox, "allowed_senders": senders,
                "accept_all": accept_all, "require_tag": False,
                "since": datetime.now(timezone.utc).isoformat(), "hitl": False, "allow_samples": args.allow_samples})
    print("Configuration saved. Next: python -m visa_agent.qq_mail probe --data " + str(args.data))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not print credential-bearing provider errors.
        print("配置未保存完成：" + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
        raise SystemExit(1)
