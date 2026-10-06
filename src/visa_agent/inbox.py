"""Durable channel -> sender -> conversation -> case binding for a local connector.

receive_simulated is explicitly a simulator. receive_signed authenticates an
internal connector, NOT mailbox ownership or a Twilio/SendGrid webhook. Real
provider adapters must verify their provider signature before signing this handoff.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import time
from typing import Literal
import uuid

from email_validator import validate_email
from pydantic import Field, field_validator

from .conversation import language_for, reply_for
from .documents import stage_file
from .store import digest
from .types import Case, CaseEvent, StrictModel


class Incoming(StrictModel):
    channel: Literal["web", "email", "whatsapp"]
    account: str = Field(min_length=1, max_length=120)
    thread: str = Field(min_length=1, max_length=200)
    sender: str = Field(min_length=1, max_length=254)
    message_id: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=12000)
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("account", "thread", "sender", "message_id")
    @classmethod
    def no_controls(cls, value):
        if any(ord(c) < 32 for c in value) or value != value.strip():
            raise ValueError("Routing identifiers cannot contain control characters or surrounding spaces")
        return value

    @field_validator("at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Message time must include timezone")
        return value.astimezone(timezone.utc)


def normalize_sender(channel, sender):
    if channel == "email":
        # Do not merge plus aliases, dots, or differently cased local parts.
        return validate_email(sender, check_deliverability=False).normalized
    if channel == "whatsapp":
        sender = sender.removeprefix("whatsapp:")
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", sender):
            raise ValueError("WhatsApp sender must be a complete E.164 number, e.g. +8613812345678")
    elif not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", sender):
        raise ValueError("Web sender must be the server-issued workspace identity")
    return sender


class Inbox:
    def __init__(self, service, *, connector_secret=None):
        self.service, self.store = service, service.store
        self.secret = connector_secret

    def receive_signed(self, raw: bytes, timestamp: str, signature: str, *, now=None):
        """Raw-body HMAC contract for an authenticated INTERNAL connector only."""
        if not self.secret or len(self.secret) < 32:
            raise ValueError("Configure an internal connector secret of at least 32 bytes")
        if len(raw) > 100_000 or not timestamp.isdigit():
            raise ValueError("Invalid connector envelope")
        if abs((now if now is not None else time.time()) - int(timestamp)) > 300:
            raise ValueError("Connector signature timestamp expired")
        wanted = hmac.new(self.secret, timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(wanted, signature):
            raise ValueError("Invalid connector signature")
        incoming = Incoming.model_validate_json(raw)
        return self._receive(incoming, [], proof="internal_connector_hmac")

    def receive_simulated(self, incoming: Incoming, attachments=(), *, test_mode=False):
        return self._receive(incoming, attachments, proof="local_simulation", test_mode=test_mode)

    def receive_connector(self, incoming: Incoming, attachments=(), *, provider="graph", test_mode=False):
        """Internal call after provider retrieval, never a public HTTP endpoint."""
        proofs = {"graph": "graph_mailbox_oauth_test_allowlist", "imap": "imap_mailbox_login"}
        return self._receive(incoming, attachments, proof=proofs[provider], test_mode=test_mode)

    def session(self, session_id):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM inbox_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown conversation")
        return dict(row)

    def _receive(self, incoming, attachments, *, proof, test_mode=False):
        if len(attachments) > 5:
            raise ValueError("At most five attachments per message")
        sender = normalize_sender(incoming.channel, incoming.sender)
        # Account namespaces stop equal thread/message ids in two mailboxes colliding.
        sid = digest([incoming.channel, incoming.account, incoming.thread])
        delivery_id = digest([incoming.channel, incoming.account, incoming.message_id])
        staged = [stage_file(path, self.store.root) for path in attachments]
        body = incoming.model_dump(mode="json")
        body.pop("at")  # Retried delivery timestamps are not business content.
        body["sender"] = sender
        fingerprint = digest({**body, "files": [sha for sha, _ in staged]})
        command = incoming.text.strip().lower()
        if command in {"/exit", "/reset", "/start", "/status", "/help"} and attachments:
            raise ValueError("Send session commands separately from attachments")
        with self.store.transaction() as db:
            session = db.execute("SELECT * FROM inbox_sessions WHERE id=?", (sid,)).fetchone()
            if session and session["sender"] != sender:
                raise ValueError("Sender does not own this conversation; open a separate thread")
            prior = db.execute("SELECT * FROM inbox_deliveries WHERE id=?", (delivery_id,)).fetchone()
            if prior:
                if prior["input_hash"] != fingerprint or prior["session_id"] != sid:
                    raise ValueError("Message ID reused with a different sender, conversation or payload")
                if prior["result"]:
                    return {**json.loads(prior["result"]), "duplicate": True}
                case_id = prior["case_id"]  # Restart resumes the pinned case, never a new generation.
            else:
                if not session:
                    case_id = "case-" + uuid.uuid4().hex
                    case = Case(id=case_id, test_mode=test_mode, hitl_enabled=self.service.hitl_enabled,
                                application_forms=self.service.application_forms)
                    db.execute("INSERT INTO cases VALUES (?,?)", (case_id, case.model_dump_json()))
                    db.execute("INSERT INTO inbox_sessions VALUES (?,?,?,?,?,'active',?)",
                               (sid, incoming.channel, incoming.account, incoming.thread, sender, case_id))
                else:
                    case_id = session["case_id"]
                db.execute("INSERT INTO inbox_deliveries VALUES (?,?,?,?,NULL)",
                           (delivery_id, sid, fingerprint, case_id))
            case = self.store.get(case_id, db)
            case.language = language_for(incoming.text, case.language)
            reply = None
            if command in {"/reset", "/start"}:
                if session:
                    case.conversation_closed = True
                    self.store.save(case, db)
                    case = Case(id="case-" + uuid.uuid4().hex, language=case.language, test_mode=test_mode,
                                hitl_enabled=self.service.hitl_enabled, application_forms=self.service.application_forms)
                    db.execute("INSERT INTO cases VALUES (?,?)", (case.id, case.model_dump_json()))
                db.execute("UPDATE inbox_sessions SET case_id=?,state='active' WHERE id=?", (case.id, sid))
                db.execute("UPDATE inbox_deliveries SET case_id=? WHERE id=?", (case.id, delivery_id))
                reply = ("好的，我们重新开始！已新建空白案件，旧资料仍保留供查阅，本次会从头了解您的情况。先告诉我：来英国的目的、国籍和准备从哪里申请。" if case.language == "zh" else
                         "Of course, let's start fresh! A new empty case is ready; your earlier records are kept separately. Tell me your purpose, nationality and where you will apply from.")
            elif command == "/exit":
                case.conversation_closed = True
                self.store.save(case, db)
                db.execute("UPDATE inbox_sessions SET state='closed' WHERE id=?", (sid,))
                reply = "好的，本次会话已结束。等您准备好了，发送 /start 就能开始空白案件；旧记录仍保留供查阅。" if case.language == "zh" else "Of course, this conversation is now closed. When you're ready, send /start for a fresh case. Your earlier records are kept."
            elif case.conversation_closed:
                reply = "之前的会话已结束，这条输入尚未处理。如果想继续准备，回复 /start 就可以重新开始。" if case.language == "zh" else "Your earlier conversation is closed, so this message hasn't been processed. Reply with /start whenever you're ready to begin again."
            elif command == "/help":
                reply = ("/status 查看材料进度；/exit 结束会话；/reset 清空工作上下文并新建案件；/start 开始新案件。先说明目的、国籍、申请地点，再按提示补件。" if case.language == "zh" else
                         "/status shows progress; /exit closes this conversation; /reset clears working context and starts a new case; /start opens a new case. Start with your purpose, nationality and application location.")
            elif command == "/status":
                reply = reply_for(case, intent="status", received_count=0)
            if reply is not None:
                result = {"session_id": sid, "case_id": case.id, "session_state": "closed" if case.conversation_closed else "active",
                          "proof": proof, "reply": reply, "command": command, "duplicate": False,
                          "status": case.status.value, "run_id": delivery_id, "version": case.version, "error": None}
                db.execute("UPDATE inbox_deliveries SET result=? WHERE id=?", (json.dumps(result, ensure_ascii=False), delivery_id))
                self.store.record_run(case.id, delivery_id, {"command": command, "routing": body,
                    "identity_proof": proof, "after": case.model_dump(mode="json"), "reply": reply}, db)
                return result
        # The business inbox is independently idempotent, so a crash here is safe to retry.
        event = CaseEvent(case_id=case_id, event_id=delivery_id, text=incoming.text, at=incoming.at,
                          kind="upload" if attachments else "message", attachments=[str(p) for p in attachments])
        turn = self.service.handle_event(event)
        result = {**turn.model_dump(mode="json"), "session_id": sid, "session_state": self.session(sid)["state"],
                  "proof": proof, "command": None}
        with self.store.transaction() as db:
            # Failed business events remain retryable, without creating another case.
            if not turn.error:
                db.execute("UPDATE inbox_deliveries SET result=? WHERE id=?", (json.dumps(result, ensure_ascii=False), delivery_id))
        return result
