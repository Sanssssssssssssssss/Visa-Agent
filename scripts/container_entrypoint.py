"""Initialize a new persistent inbox once, then run the existing mail worker."""
import json
import os
from pathlib import Path
import sys

from visa_agent.config import load_environment


def initialize(data):
    load_environment()
    if not (os.getenv("VISA_API_KEY") or os.getenv("DEEPSEEK_API_KEY")):
        raise ValueError("Configure VISA_API_KEY, DEEPSEEK_API_KEY or VISA_API_KEY_FILE")
    if not os.getenv("VISA_QQ_AUTH_CODE"):
        raise ValueError("Configure VISA_QQ_AUTH_CODE or VISA_QQ_AUTH_CODE_FILE")
    if not os.getenv("VISA_QQ_MAILBOX"):
        raise ValueError("Configure VISA_QQ_MAILBOX")
    config_path = data / "qq-config.json"
    if config_path.exists():
        from visa_agent.inbox import normalize_sender
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config["mailbox"] != normalize_sender("email", os.environ["VISA_QQ_MAILBOX"]):
            raise ValueError("Mailbox differs from persisted configuration; use a separate data volume")
        return
    from configure_qq import main as configure
    sys.argv = ["configure_qq", "--from-env", "--data", str(data)]
    configure()


def main():
    action = sys.argv[1:] or ["mail"]
    if action[0] not in {"mail", "setup"}:
        os.execvp(action[0], action)
    data = Path(os.getenv("VISA_QQ_DATA_DIR", "/data"))
    initialize(data)
    if action[0] == "setup":
        return
    from visa_agent.qq_mail import main as watch
    sys.argv = ["qq_mail", "watch", "--data", str(data), "--send-replies"]
    watch()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Container startup failed: " + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__), flush=True)
        raise SystemExit(1)
