"""Local liveness/poll freshness; never call the model or send mail."""
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from visa_agent.worker import worker_status


def main():
    status = worker_status(Path(os.getenv("VISA_QQ_DATA_DIR", "/data")))
    if not status["running"] or status["stop_requested"]:
        return 1
    stamp = status.get("last_poll", {}).get("at") or status.get("process", {}).get("started_at")
    if not stamp:
        return 1
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds()
    return 0 if 0 <= age <= 1800 else 1


if __name__ == "__main__":
    sys.exit(main())
