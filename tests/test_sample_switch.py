"""Local sample policy affects case creation; it never bypasses missing evidence."""
from datetime import datetime, timezone
from email.message import EmailMessage
import json
from pathlib import Path
from types import SimpleNamespace

from visa_agent.qq_mail import QQInbox
from visa_agent.service import VisaService
from visa_agent.store import write_json

DATA = Path(__file__).resolve().parents[1] / "datasets"


def test_sample_policy_complete_missing_new_case_and_reset(tmp_path):
    service = VisaService(tmp_path, "offline", hitl=False, application_forms=True)
    sent = []
    connection = SimpleNamespace(send=lambda message, to: sent.append(message))

    def receive(id, *, samples, files=(), text="route: visitor", parent=None):
        message = EmailMessage()
        message["From"], message["To"] = "applicant@example.org", "12345@qq.com"
        message["Message-ID"], message["Subject"] = f"<{id}@example.org>", "Visa documents"
        if parent:
            message["In-Reply-To"] = f"<{parent}@example.org>"
        message.set_content(text)
        for file in files:
            message.add_attachment(file.read_bytes(), maintype="application", subtype="octet-stream", filename=file.name)
        # Recreate adapter/service boundary as each provider poll does.
        adapter = QQInbox(service, connection, "12345@qq.com", require_tag=False, allow_samples=samples)
        return adapter.receive(message.as_bytes(), datetime.now(timezone.utc), send_replies=True)["result"]

    form = DATA / "intake/visitor-example-TEST-ONLY.xlsx"
    docs = sorted((DATA / "materials/dev_visitor").glob("*.pdf"))
    partial = receive("partial", samples=True, files=[form, docs[0]])
    assert partial["status"] == "WAIT_USER" and not partial["pack_path"]
    complete = receive("complete", samples=True, files=[form, *docs])
    assert complete["status"] == "COMPLETE" and service.store.get(complete["case_id"]).test_mode
    assert "演示案件" in complete["reply"]
    assert any(a.get_filename() == "visa-materials.zip" for a in sent[-1].iter_attachments())
    normal = receive("normal", samples=False, files=[form, *docs], text="route: visitor\nallow_samples: true")
    assert normal["status"] == "WAIT_USER" and not service.store.get(normal["case_id"]).test_mode
    assert not normal["pack_path"]
    old = receive("old", samples=False, parent="complete", text="/status")
    assert old["case_id"] == complete["case_id"] and service.store.get(old["case_id"]).test_mode
    reset = receive("reset", samples=False, parent="complete", text="/reset")
    assert reset["case_id"] != complete["case_id"] and not service.store.get(reset["case_id"]).test_mode
    assert service.store.get(complete["case_id"]).conversation_closed


def test_cli_setting_needs_no_secret_and_worker_reloads_it(tmp_path, monkeypatch):
    import visa_agent.qq_mail as module

    config_path = tmp_path / "qq-config.json"
    write_json(config_path, {"mailbox": "12345@qq.com", "accept_all": True})
    monkeypatch.setattr(module, "build_encrypted_persistence", lambda _: (_ for _ in ()).throw(AssertionError("No secret needed")))
    monkeypatch.setattr("sys.argv", ["qq_mail", "samples", "--data", str(tmp_path), "--allow-samples", "on"])
    module.main()
    assert json.loads(config_path.read_text())["allow_samples"] is True
    seen = []

    def poll(args, config, secret, budget):
        seen.append(config["allow_samples"])
        if len(seen) == 1:
            write_json(config_path, {**config, "allow_samples": False})
        else:
            (tmp_path / "qq-stop").touch()
        return {"messages": []}

    monkeypatch.setattr(module, "build_encrypted_persistence", lambda _: SimpleNamespace(load=lambda: "local-test"))
    monkeypatch.setattr(module, "receive_once", poll)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr("sys.argv", ["qq_mail", "watch", "--data", str(tmp_path)])
    module.main()
    assert seen == [True, False]
