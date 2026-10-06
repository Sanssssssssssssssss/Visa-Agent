"""Exercise all three routes across the MIME boundary, including the final attachment."""
from datetime import datetime, timezone
from email.message import EmailMessage
import hashlib
from io import BytesIO
import json
from pathlib import Path
import zipfile

import pytest

from visa_agent.delivery import verify_pack
from visa_agent.qq_mail import QQInbox
from visa_agent.service import VisaService
from visa_agent.submission import APPLICATIONS

DATA = Path(__file__).resolve().parents[1] / "datasets"


@pytest.mark.parametrize("route", ["visitor", "student", "skilled_worker"])
def test_partial_then_complete_pack_delivered_to_same_sender(tmp_path, route):
    class Connection:
        def __init__(self):
            self.sent = []

        def send(self, message, recipient):
            self.sent.append((message, recipient))

    service = VisaService(tmp_path, "offline", hitl=False, application_forms=True)
    conn = Connection()
    inbox = QQInbox(service, conn, "12345@qq.com", require_tag=False, allow_samples=True)

    def send(index, text, files=()):
        mail = EmailMessage()
        mail["From"], mail["To"] = "applicant@example.org", "12345@qq.com"
        mail["Subject"], mail["Message-ID"] = "Application", f"<m{index}@example.org>"
        if conn.sent:
            mail["In-Reply-To"] = conn.sent[-1][0]["Message-ID"]
        mail.set_content(text)
        for path in files:
            mail.add_attachment(path.read_bytes(), maintype="application", subtype="octet-stream", filename=path.name)
        return inbox.receive(mail.as_bytes(), datetime.now(timezone.utc), send_replies=True)

    first = send(1, f"route: {route}")
    case_id = first["result"]["case_id"]
    assert service.store.get(case_id).test_mode
    docs = sorted((DATA / "materials" / f"dev_{route}").glob("*.pdf"))
    second = send(2, "表填好了，先发这些。", [DATA / "intake" / f"{route}-example-TEST-ONLY.xlsx", docs[0]])
    assert second["result"]["status"] != "COMPLETE"
    assert second["result"]["form_path"] is None
    assert "填写 C 列" not in second["result"]["reply"]
    assert all(a.get_content_type() != "application/zip" for a in conn.sent[-1][0].iter_attachments())
    last = send(3, "剩下的材料也准备好了。", docs[1:])
    assert last["send_status"] == "sent" and last["result"]["status"] == "COMPLETE"
    assert last["result"]["case_id"] == case_id
    mail, recipient = conn.sent[-1]
    assert recipient == "applicant@example.org"
    assert "visa-materials.zip" in mail.get_body(preferencelist=("plain",)).get_content()
    assert APPLICATIONS[route] in mail.get_body(preferencelist=("plain",)).get_content()
    attachment = next(a for a in mail.iter_attachments() if a.get_filename() == "visa-materials.zip")
    case = service.store.get(case_id)
    assert attachment.get_payload(decode=True) == Path(case.pack_path).read_bytes()
    verify_pack(case)
    with zipfile.ZipFile(BytesIO(attachment.get_payload(decode=True))) as archive:
        assert archive.testzip() is None
        assert "application-information.xlsx" in archive.namelist()
        assert "DEMO ONLY" in archive.read("START-HERE.html").decode()
        assert APPLICATIONS[route] in archive.read("submission-guide.txt").decode()
        content = json.loads(archive.read("manifest.json"))
        assert len(content["documents"]) == len(docs) + 1
        for doc in content["documents"]:
            assert hashlib.sha256(archive.read(doc["archive_path"])).hexdigest() == doc["sha256"]
        entries = {name: archive.read(name) for name in archive.namelist()}
    # A swapped handover could direct customers to a phishing/payment page.
    entries["submission-guide.txt"] = b"Visit https://example.org/fake-payment"
    with zipfile.ZipFile(case.pack_path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    with pytest.raises(ValueError, match="handover"):
        verify_pack(case)
