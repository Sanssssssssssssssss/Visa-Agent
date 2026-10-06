"""Start, stop or inspect the local mail worker without opening a product UI."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from visa_agent.worker import worker_status

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--data", type=Path, default=ROOT / "data/qq-test")
    parser.add_argument("--hitl", choices=["on", "off"], default="off")
    parser.add_argument("--wait", type=int, default=0, help="With stop, wait up to this many seconds for the worker lock")
    args = parser.parse_args()
    data = args.data.resolve()
    if args.action == "stop":
        data.mkdir(parents=True, exist_ok=True)
        (data / "qq-stop").touch()
        print("Stop requested. The current event will finish first.")
        deadline = time.monotonic() + args.wait
        while args.wait and worker_status(data)["running"]:
            if time.monotonic() >= deadline:
                raise SystemExit("Worker is still finishing an event; inspect before restarting.")
            time.sleep(1)
        return
    status = worker_status(data)
    if args.action == "status" or status["running"]:
        print(json.dumps(status, indent=2))
        return
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    with (data / "worker.stdout.log").open("ab") as stdout, (data / "worker.stderr.log").open("ab") as stderr:
        process = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "visa_agent.qq_mail", "watch",
            "--data", str(data), "--hitl", args.hitl, "--send-replies"], cwd=ROOT,
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, **options)
    for _ in range(50):
        if process.poll() is not None:
            raise SystemExit("Worker exited. Check the local worker logs; no credentials are printed here.")
        status = worker_status(data)
        if status["running"]:
            print(json.dumps(status, indent=2))
            return
        time.sleep(0.1)
    raise SystemExit("Startup is taking longer than expected. Inspect status and logs before starting again.")


if __name__ == "__main__":
    main()
