"""Packaged service instructions, prepended to both model phases."""
import hashlib
from pathlib import Path

SOUL = Path(__file__).with_name("prompts").joinpath("SOUL.md").read_text(encoding="utf-8").strip()
SOUL_HASH = hashlib.sha256(SOUL.encode("utf-8")).hexdigest()
