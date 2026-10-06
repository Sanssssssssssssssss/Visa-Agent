"""Container-only offline acceptance: OCR, delivery, persistence and boot/stop.

Run with no model/mail credentials. It uses its own /tmp test roots and fixture
messages. It never connects to the QQ inbox or calls a paid API.
"""
import hashlib
import importlib.metadata
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from pydantic_ai import models

from visa_agent.documents import read_document
from visa_agent.replay import dataset_path, replay
from visa_agent.service import VisaService
from visa_agent.types import CaseEvent

from manage_data import backup, restore

ROOT = Path(__file__).resolve().parents[1]


def check():
    models.ALLOW_MODEL_REQUESTS = False
    assert os.getuid() != 0, "Run smoke as the production image's non-root user"
    result = {"uid": os.getuid(), "model_requests": 0, "mail_sends": 0, "routes": {},
              "packages": {p: importlib.metadata.version(p) for p in ("rapidocr", "pypdf", "pypdfium2", "pydantic-ai-slim")}}
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for route in ("visitor", "student", "skilled_worker"):
            report = replay(VisaService(work / route, "offline", hitl=True),
                            ROOT / f"datasets/cases/dev_{route}.json", approve_demo=True)
            assert report["passed"] and report["pack_path"]
            auto = VisaService(work / (route + "-auto"), "offline", hitl=False)
            auto.create_case(route, test_mode=True)
            scenario = json.loads((ROOT / f"datasets/cases/dev_{route}.json").read_text(encoding="utf-8"))
            for index, event in enumerate(scenario["events"]):
                turn = auto.handle_event(CaseEvent(case_id=route, event_id=str(index), text=event["text"],
                    attachments=[str(dataset_path(ROOT / "datasets", p)) for p in event["attachments"]]))
                assert not turn.error
            assert turn.status == "COMPLETE"
            from visa_agent.delivery import verify_pack
            verify_pack(auto.store.get(route))
            result["routes"][route] = "reviewed_and_automatic_zip_verified"
        for name in ("identity.jpg", "funds-scan.pdf"):
            path = ROOT / "datasets/formatted-materials-v2/student" / name
            doc = read_document(path, hashlib.sha256(path.read_bytes()).hexdigest(), name)
            assert not doc.problems and "Mei Example" in doc.pages[0].text
            result[name] = {"pages": len(doc.pages), "method": doc.pages[0].method}
        archive = work / "cases.tar.gz"
        backup(work / "visitor", archive)
        (work / "visitor").rename(work / "preserved-visitor")
        restore(work / "visitor", archive)
        with VisaService(work / "visitor", "offline", hitl=False).store.connect() as db:
            case_id = db.execute("SELECT id FROM cases").fetchone()[0]
        from visa_agent.delivery import verify_pack
        verify_pack(VisaService(work / "visitor", "offline", hitl=False).store.get(case_id))
        result["backup_restore"] = "persisted_case_restored"

        data = work / "mail"
        env = {**os.environ, "VISA_QQ_DATA_DIR": str(data), "VISA_API_KEY": "offline-test-key",
               "VISA_QQ_AUTH_CODE": "abcdefghijklmnop", "VISA_QQ_MAILBOX": "12345@qq.com",
               "VISA_QQ_ACCEPT_ALL": "1", "PYTHON_DOTENV_DISABLED": "1"}
        setup = [sys.executable, str(ROOT / "scripts/container_entrypoint.py"), "setup"]
        subprocess.run(setup, env=env, check=True, stdout=subprocess.DEVNULL)
        original = (data / "qq-config.json").read_bytes()
        subprocess.run(setup, env=env, check=True, stdout=subprocess.DEVNULL)
        assert original == (data / "qq-config.json").read_bytes()
        result["repeated_setup"] = "cursor_start_unchanged"
        # Run the real watch loop with an offline provider function. SIGTERM must
        # reach the graceful handler, release the lock and exit without a kill.
        fake_watch = work / "watch.py"
        fake_watch.write_text("""from pathlib import Path
import sys
from visa_agent import qq_mail
def receive(args, config, secret, budget):
    Path(args.data, 'fake-poll-ready').touch()
    return {'messages': [], 'scanned': 0}
qq_mail.receive_once = receive
sys.argv = ['watch', 'watch', '--data', sys.argv[1]]
qq_mail.main()
""", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(fake_watch), str(data)], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 15
            while not (data / "fake-poll-ready").exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Offline watch did not become ready")
                time.sleep(0.1)
            subprocess.run([sys.executable, str(ROOT / "scripts/container_healthcheck.py")], env=env, check=True)
            process.send_signal(signal.SIGTERM)
            assert process.wait(timeout=20) == 0
            result["sigterm"] = "graceful_exit"
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        assert (data / "qq-stop").exists()
    return result


def main():
    with redirect_stdout(sys.stderr):
        result = check()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
