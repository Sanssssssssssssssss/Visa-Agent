"""Deployment options are operator controlled, never inferred from messages."""
import os
from pathlib import Path

from dotenv import load_dotenv


def load_environment(path=None):
    """Explicit file > VISA_ENV_FILE > cwd/.env; existing environment wins."""
    target = Path(path or os.getenv("VISA_ENV_FILE") or Path.cwd() / ".env")
    loaded = load_dotenv(target, override=False, encoding="utf-8-sig")
    for key in ("VISA_API_KEY", "DEEPSEEK_API_KEY", "VISA_QQ_AUTH_CODE"):
        secret_file = os.getenv(key + "_FILE")
        if not os.getenv(key) and secret_file:
            value = Path(secret_file).read_text(encoding="utf-8-sig").strip()
            if not value:
                raise ValueError(f"{key}_FILE is empty")
            os.environ[key] = value
    return loaded


def resolve_hitl(value=None):
    value = os.getenv("VISA_HITL", "on") if value is None else value
    if isinstance(value, bool):
        return value
    if value not in {"on", "off"}:
        raise ValueError("VISA_HITL / --hitl must be on or off")
    return value == "on"
