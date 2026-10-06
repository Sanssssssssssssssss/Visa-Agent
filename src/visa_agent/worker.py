"""One mail poller per local data directory; OS releases the lock after a crash."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .store import write_json


def _lock(handle):
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle):
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _open_lock(data):
    data.mkdir(parents=True, exist_ok=True)
    # msvcrt locks at the OS file offset; a buffered seek can leave it elsewhere.
    handle = (data / "worker.lock").open("a+b", buffering=0)
    if handle.seek(0, 2) == 0:
        handle.write(b"0")
        handle.flush()
    return handle


@contextmanager
def mail_worker_lock(data):
    with _open_lock(data) as handle:
        try:
            _lock(handle)
        except OSError:
            raise ValueError("A mail worker already owns this data directory") from None
        try:
            write_json(data / "worker.json", {"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()})
            yield
        finally:
            _unlock(handle)


def worker_status(data: Path):
    with _open_lock(data) as handle:
        try:
            _lock(handle)
        except OSError:
            running = True
        else:
            running = False
            _unlock(handle)
    result = {"running": running, "stop_requested": (data / "qq-stop").exists()}
    for name, key in (("worker.json", "process"), ("qq-watch-last.json", "last_poll")):
        path = data / name
        if path.exists():
            body = json.loads(path.read_text(encoding="utf-8"))
            # Status can be shared without including customer text, filenames or addresses.
            allowed = {"pid", "started_at", "at", "scanned", "model_requests", "error_type", "network_failures", "retry_after_seconds", "allow_samples_for_new_cases"}
            result[key] = {k: v for k, v in body.items() if k in allowed}
    return result
