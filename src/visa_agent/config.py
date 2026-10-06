"""Deployment options are operator controlled, never inferred from messages."""
import os


def resolve_hitl(value=None):
    value = os.getenv("VISA_HITL", "on") if value is None else value
    if isinstance(value, bool):
        return value
    if value not in {"on", "off"}:
        raise ValueError("VISA_HITL / --hitl must be on or off")
    return value == "on"
