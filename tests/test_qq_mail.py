from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import pytest

from visa_agent.mime_mail import MAX_MAIL_BYTES, parse_mail
from visa_agent.qq_mail import QQConnection, QQInbox
from visa_agent.service import VisaService

AT = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)


def mail(id="1", sender="lin@example.com", text="applicant_name: Lin", parent=None):
    message = EmailMessage()
    message["From"], message["To"] = sender, "12345@qq.com"
    message["Subject"] = "[VisaTest] 英国签证咨询"
    message["Message-ID"] = f"<{id}@example.com>"
    if parent:
        message["In-Reply-To"] = parent
    message.set_content(text)
    return message


class Connection:
    uidvalidity = 1

    def __init__(self, messages):
        self.messages, self.sent, self.downloads = messages, [], []
        self.failure = False

    def uids(self, since, after):
        return [uid for uid in sorted(self.messages) if uid > after][:100]

    def header(self, uid):
        raw = self.messages[uid].as_bytes()
        return raw.split(b"\n\n", 1)[0] + b"\n\n", len(raw), AT + timedelta(minutes=uid)

    def body(self, uid):
        self.downloads.append(uid)
        return self.messages[uid].as_bytes()

    def send(self, message, recipient):
        self.sent.append((message, recipient))
        if self.failure:
            raise TimeoutError("Lost response")


def adapter(tmp_path, conn):
    return QQInbox(VisaService(tmp_path, "offline", hitl=False), conn, "12345@qq.com", ["lin@example.com", "bo@example.com"])


def test_read_chinese_pdf_then_reply_in_same_thread_after_restart(tmp_path):
    message = mail(text="route: visitor\napplicant_name: Lin Example")
    content = (Path(__file__).resolve().parents[1] / "datasets/materials/dev_visitor/identity.pdf").read_bytes()
    message.add_attachment(content, maintype="application", subtype="pdf", filename="护照.pdf")
    conn = Connection({1: message})
    app = adapter(tmp_path, conn)
    result = app.poll(AT.isoformat())["messages"][0]
    assert result["send_status"] == "prepared" and not conn.sent
    case_id = result["result"]["case_id"]
    case = app.service.store.get(case_id)
    assert len(case.documents) == 1 and case.documents[0].content_role == "sample"
    assert case.documents[0].name == "护照.pdf"
    adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)
    assert len(conn.sent) == 1 and conn.sent[0][1] == "lin@example.com"
    response = conn.sent[0][0]
    assert response["In-Reply-To"] == message["Message-ID"]
    assert response["Auto-Submitted"] == "auto-replied"
    assert response.get_content().strip() == result["result"]["reply"]
    conn.messages[2] = mail("2", text="age: 30", parent=response["Message-ID"])
    next_result = adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)["messages"][0]
    assert next_result["result"]["case_id"] == case_id and len(conn.sent) == 2
    assert adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)["messages"] == []


def test_same_named_mail_attachments_keep_original_names_and_distinct_bytes(tmp_path):
    import hashlib
    message = mail()
    root = Path(__file__).resolve().parents[1] / "datasets/materials/dev_visitor"
    contents = [(root / filename).read_bytes() for filename in ("identity.pdf", "funds.pdf")]
    for content in contents:
        message.add_attachment(content, maintype="application", subtype="pdf", filename="材料.pdf")
    app = adapter(tmp_path, Connection({1: message}))
    result = app.poll(AT.isoformat())["messages"][0]["result"]
    docs = app.service.store.get(result["case_id"]).documents
    assert len(docs) == 2 and {d.name for d in docs} == {"材料.pdf"}
    assert {Path(d.path).read_bytes() for d in docs} == set(contents)
    assert {d.sha256 for d in docs} == {hashlib.sha256(content).hexdigest() for content in contents}


def test_duplicate_rfc_message_across_new_uidvalidity_does_not_resend(tmp_path):
    conn = Connection({1: mail()})
    adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)
    conn.uidvalidity = 2
    adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)
    assert len(conn.sent) == 1
    changed = mail(text="applicant_name: Mallory")
    conn.messages[2] = changed
    result = adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)
    assert result["messages"][0]["send_status"] == "rejected" and len(conn.sent) == 1


def test_reference_hijack_is_rejected_and_other_sender_gets_separate_case(tmp_path):
    conn = Connection({1: mail()})
    first = adapter(tmp_path, conn).poll(AT.isoformat())["messages"][0]["result"]
    conn.messages[2] = mail("2", sender="bo@example.com", parent="<1@example.com>")
    conn.messages[3] = mail("3", sender="bo@example.com")
    rows = adapter(tmp_path, conn).poll(AT.isoformat())["messages"]
    assert rows[0]["send_status"] == "rejected"
    assert rows[1]["result"]["case_id"] != first["case_id"]


def test_uncertain_smtp_delivery_retries_after_restart_with_same_message_id(tmp_path):
    conn = Connection({1: mail()})
    conn.failure = True
    app = adapter(tmp_path, conn)
    first = app.poll(AT.isoformat(), send_replies=True)["messages"][0]
    assert first["send_status"] == "retry" and first["retry_after_seconds"] == 15
    conn.failure = False
    assert not adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)["messages"]
    assert len(conn.sent) == 1
    with app.service.store.transaction() as db:
        db.execute("UPDATE mail_attempts SET next_attempt=0")
    rows = adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)["messages"]
    assert rows[0]["send_status"] == "sent" and len(conn.sent) == 2
    assert conn.sent[0][0]["Message-ID"] == conn.sent[1][0]["Message-ID"]
    assert not adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)["messages"]


@pytest.mark.parametrize("text,explanation", [("我想申请签证", "抱歉"), ("I want to apply for a visa", "Sorry")])
def test_failed_model_check_emails_explanation_without_claiming_success_or_resending(tmp_path, text, explanation):
    from pydantic_ai.models.function import FunctionModel
    from visa_agent.types import Status

    def unavailable(messages, info):
        raise RuntimeError("Test provider unavailable; internal diagnostic must not enter email")

    conn = Connection({1: mail(text=text)})
    service = VisaService(tmp_path, "offline", hitl=False, model_override=FunctionModel(unavailable))
    inbox = QQInbox(service, conn, "12345@qq.com", ["lin@example.com"])
    row = inbox.poll(AT.isoformat(), send_replies=True)["messages"][0]
    result = row["result"]
    assert result["error"] and result["status"] == "BLOCKED" and not result["pack_path"]
    assert row["send_status"] == "sent" and len(conn.sent) == 1
    body = conn.sent[0][0].get_content()
    assert explanation in body and "internal diagnostic" not in body
    assert service.store.get(result["case_id"]).status == Status.BLOCKED
    assert service.store.events(result["case_id"])[0]["status"] == "failed"
    assert not inbox.poll(AT.isoformat(), send_replies=True)["messages"]
    assert len(conn.sent) == 1


def test_unsupported_attachment_gets_reply_and_does_not_count_as_evidence(tmp_path):
    message = mail(text="这是我的材料，请看看")
    message.add_attachment(b"not a supported file", maintype="application", subtype="octet-stream", filename="example.exe")
    conn = Connection({1: message})
    app = adapter(tmp_path, conn)
    row = app.poll(AT.isoformat(), send_replies=True)["messages"][0]
    assert row["send_status"] == "sent" and row["result"]["reply"]
    case = app.service.store.get(row["result"]["case_id"])
    assert not case.documents and not case.pack_path
    assert any(c.id.startswith("input:") and c.status == "fail" for c in case.checks)
    assert not app.poll(AT.isoformat(), send_replies=True)["messages"]


@pytest.mark.parametrize("args", [{"document_id": "another-cases-file", "page": 1},
                                  {"document_id": "missing", "page": "not-a-page"}])
def test_tool_failures_still_send_a_reply_without_internal_details(tmp_path, args):
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    def broken_tool(messages, info):
        return ModelResponse(parts=[ToolCallPart("read_evidence", args)])
    conn = Connection({1: mail(text="我上传的材料看到了吗？")})
    app = QQInbox(VisaService(tmp_path, "offline", hitl=False, model_override=FunctionModel(broken_tool)),
                  conn, "12345@qq.com", ["lin@example.com"])
    row = app.poll(AT.isoformat(), send_replies=True)["messages"][0]
    assert row["send_status"] == "sent" and row["result"]["error"]
    assert row["result"]["status"] == "BLOCKED" and not row["result"]["pack_path"]
    assert "another-cases-file" not in conn.sent[0][0].get_content()
    assert "not-a-page" not in conn.sent[0][0].get_content()
    assert len(conn.sent) == 1


def test_stale_prepared_reply_not_sent_after_exit(tmp_path):
    conn = Connection({1: mail()})
    adapter(tmp_path, conn).poll(AT.isoformat())
    conn.messages[2] = mail("2", text="/exit", parent="<1@example.com>")
    adapter(tmp_path, conn).poll(AT.isoformat())
    rows = adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)["messages"]
    assert [r["send_status"] for r in rows] == ["superseded", "sent"]
    assert len(conn.sent) == 1


def test_prepared_reply_is_not_sent_after_material_rules_change(tmp_path, monkeypatch):
    import visa_agent.mail_outbox as outbox

    conn = Connection({1: mail()})
    app = adapter(tmp_path, conn)
    prepared = app.poll(AT.isoformat())["messages"][0]
    assert prepared["send_status"] == "prepared"
    monkeypatch.setattr(outbox, "RULE_VERSION", "different-material-rules")
    result = app.poll(AT.isoformat(), send_replies=True)["messages"][0]
    assert result["send_status"] == "superseded" and not conn.sent


@pytest.mark.parametrize("header,value", [("Reply-To", "third@example.com"), ("Sender", "third@example.com"),
    ("Auto-Submitted", "auto-replied"), ("List-ID", "list.example.com")])
def test_bad_envelopes_never_create_case(tmp_path, header, value):
    message = mail()
    message[header] = value
    conn = Connection({1: message})
    app = adapter(tmp_path, conn)
    assert app.poll(AT.isoformat(), send_replies=True)["messages"][0]["send_status"] == "rejected"
    with app.service.store.connect() as db:
        assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 0
    assert not conn.sent


def test_unrelated_mail_body_is_not_downloaded(tmp_path):
    message = mail()
    message.replace_header("Subject", "Personal message")
    conn = Connection({1: message, 2: mail("2", sender="unknown@example.com")})
    assert adapter(tmp_path, conn).poll(AT.isoformat())["messages"] == []
    assert conn.downloads == []


def test_html_reply_removes_outlook_history_and_remote_content():
    message = mail(text="unused")
    message.clear_content()
    message.set_content('<div>我想去英国旅游。</div><script>bad()</script><img src="https://example.com/pixel">'
                        '<div id="divRplyFwdMsg">From: earlier</div><div>age: 99</div>', subtype="html")
    parsed = parse_mail(message.as_bytes(), "12345@qq.com", {"lin@example.com"})
    assert parsed["text"] == "我想去英国旅游。"


@pytest.mark.parametrize("quote", ["On Monday Lin wrote:", "在 2026 年 10 月 5 日写道：", "发件人：Agent", "> old reply"])
def test_plain_reply_excludes_quoted_model_or_customer_text(quote):
    message = mail(text="age: 30\n\n" + quote + "\napplicant_name: Wrong")
    result = parse_mail(message.as_bytes(), "12345@qq.com", {"lin@example.com"})
    assert result["text"] == "age: 30"


def test_outlook_plain_reply_separator_does_not_hide_reset_command(tmp_path):
    conn = Connection({1: mail()})
    app = adapter(tmp_path, conn)
    old = app.poll(AT.isoformat())["messages"][0]["result"]
    conn.messages[2] = mail("2", text="/reset\n________________________________\n发件人: Agent\nold reply",
                            parent="<1@example.com>")
    result = adapter(tmp_path, conn).poll(AT.isoformat())["messages"][0]["result"]
    assert result["command"] == "/reset" and result["case_id"] != old["case_id"]
    assert app.service.store.get(result["case_id"]).history_count == 0
    assert all(t.get("command") == "/reset" for t in app.service.store.traces(result["case_id"]))


def test_oversized_mail_is_not_downloaded(tmp_path):
    conn = Connection({1: mail()})
    raw, _, at = conn.header(1)
    conn.header = lambda uid: (raw, MAX_MAIL_BYTES + 1, at)
    row = adapter(tmp_path, conn).poll(AT.isoformat(), send_replies=True)["messages"][0]
    assert row["send_status"] == "sent" and row["result"]["reply"]
    assert not conn.downloads


def test_thirty_messages_restart_and_bound_history(tmp_path):
    conn = Connection({1: mail()})
    for i in range(2, 31):
        conn.messages[i] = mail(str(i), parent="<1@example.com>")
    cases = set()
    for _ in range(10):
        results = adapter(tmp_path, conn).poll(AT.isoformat(), max_messages=3, send_replies=True)["messages"]
        assert len(results) == 3
        cases.update(r["result"]["case_id"] for r in results)
    assert len(cases) == 1 and len(conn.sent) == 30
    case = adapter(tmp_path, conn).service.store.get(next(iter(cases)))
    assert len(case.history) == 20 and case.history_count == 30


def test_open_intake_accepts_new_senders_and_subjects_but_keeps_cases_separate(tmp_path):
    first = mail(sender="newperson@example.com")
    first.replace_header("Subject", "英国签证咨询")
    second = mail("2", sender="another@example.com")
    second.replace_header("Subject", "材料")
    own = mail("3", sender="12345@qq.com")
    auto = mail("4", sender="newperson@example.com")
    auto["Auto-Submitted"] = "auto-replied"
    conn = Connection({1: first, 2: second, 3: own, 4: auto})
    app = QQInbox(VisaService(tmp_path, "offline", hitl=False), conn, "12345@qq.com", require_tag=False)
    rows = app.poll(AT.isoformat(), send_replies=True)["messages"]
    assert [r["send_status"] for r in rows] == ["sent", "sent", "rejected"]
    assert rows[0]["result"]["case_id"] != rows[1]["result"]["case_id"]
    assert {to for _, to in conn.sent} == {"newperson@example.com", "another@example.com"}
    assert 3 not in conn.downloads


@pytest.mark.parametrize("day", ["6", "06", " 6"])
def test_qq_server_internaldate_single_digit_day(day):
    connection = QQConnection("12345@qq.com", "not-a-real-credential")
    metadata = f'140 (UID 153 RFC822.SIZE 10846 INTERNALDATE "{day}-Oct-2026 23:00:03 +0800" BODY[HEADER] {{10}}'.encode()
    connection._uid = lambda *args: [(metadata, b"From: test")]
    _, size, at = connection.header(153)
    assert size == 10846 and at == datetime(2026, 10, 6, 15, 0, 3, tzinfo=timezone.utc)


def test_qq_provider_notice_is_filtered_before_body_download_or_model(tmp_path):
    message = mail(sender="10000@qq.com")
    message.replace_header("Subject", "QQ 邮箱 APP 推广")
    conn = Connection({1: message})
    app = QQInbox(VisaService(tmp_path, "offline", hitl=False), conn, "12345@qq.com", require_tag=False)
    assert app.poll(AT.isoformat(), send_replies=True)["messages"] == []
    assert not conn.downloads and not conn.sent
    with app.service.store.connect() as db:
        assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 0


@pytest.mark.parametrize("filename", ["../passport.pdf", "archive.zip", "hidden.exe"])
def test_mime_attachment_boundaries(filename):
    message = mail()
    message.add_attachment(b"test", maintype="application", subtype="octet-stream", filename=filename)
    with pytest.raises(ValueError):
        parse_mail(message.as_bytes(), "12345@qq.com", {"lin@example.com"})


@pytest.mark.parametrize("exercise", ["transient_network", "budget"])
def test_worker_recovers_network_failure_and_stops_at_request_cap(tmp_path, monkeypatch, exercise):
    import json
    from types import SimpleNamespace
    import visa_agent.qq_mail as module
    (tmp_path / "qq-config.json").write_text(json.dumps({"mailbox": "12345@qq.com"}))
    monkeypatch.setattr(module, "build_encrypted_persistence", lambda path: SimpleNamespace(load=lambda: "test-only"))
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr("sys.argv", ["qq_mail", "watch", "--data", str(tmp_path), "--request-cap", "1"])
    calls = []
    def fake_poll(args, config, secret, budget):
        calls.append(1)
        if exercise == "transient_network" and len(calls) == 1:
            raise OSError("offline transport test")
        if exercise == "budget":
            budget.reserve("offline-test-accounting")
        else:
            (tmp_path / "qq-stop").touch()
        return {"messages": [], "model_requests": budget.count()}
    monkeypatch.setattr(module, "receive_once", fake_poll)
    module.main()
    assert len(calls) == (2 if exercise == "transient_network" else 1)
    state = json.loads((tmp_path / "qq-watch-last.json").read_text())
    if exercise == "budget":
        assert state["paused"] == "model_request_budget"
