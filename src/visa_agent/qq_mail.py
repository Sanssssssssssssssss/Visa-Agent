"""QQ IMAP/SMTP intake with configured sender policy and bounded polls."""
import argparse
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime
import hashlib
import imaplib
import json
from pathlib import Path
import re
import smtplib
import ssl
import time

from msal_extensions import build_encrypted_persistence

from .agent import LiveBudget
from .inbox import Inbox, Incoming, normalize_sender
from .mail_outbox import send_prepared_reply
from .mime_mail import MAX_MAIL_BYTES, SYSTEM_SENDERS, addresses, parse_mail
from .service import VisaService
from .store import digest, write_json


class QQConnection:
    """Provider boundary. Only fixed QQ TLS endpoints receive the local credential."""
    def __init__(self, mailbox, secret):
        if mailbox.split("@")[-1] not in {"qq.com", "foxmail.com"}:
            raise ValueError("This connector supports QQ/Foxmail accounts only")
        self.mailbox, self.secret = mailbox, secret
        self.imap = None

    def __enter__(self):
        self.imap = imaplib.IMAP4_SSL("imap.qq.com", 993, ssl_context=ssl.create_default_context(), timeout=30)
        try:
            self.imap.login(self.mailbox, self.secret)
            if self.imap.select("INBOX", readonly=True)[0] != "OK":
                raise ValueError("Cannot select QQ INBOX")
            value = self.imap.response("UIDVALIDITY")[1]
            self.uidvalidity = int(value[0])
        except Exception:
            self.imap.shutdown()
            raise
        return self

    def __exit__(self, *args):
        # Never expunge/delete or mark messages read.
        try:
            self.imap.logout()
        except (OSError, imaplib.IMAP4.error):
            pass

    def _uid(self, *args):
        status, data = self.imap.uid(*args)
        if status != "OK":
            raise ValueError("QQ IMAP command failed: " + args[0])
        return data

    def uids(self, since, after):
        # UID, not sequence number; midnight filtering is refined with INTERNALDATE.
        date = since.astimezone(timezone.utc)
        months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        day = f'{date.day:02d}-{months[date.month-1]}-{date.year}'
        data = self._uid("search", None, "SINCE", day, "UID", f"{after + 1}:*")
        return sorted(int(v) for v in data[0].split() if int(v) > after)[:100]

    def header(self, uid):
        data = self._uid("fetch", str(uid), "(RFC822.SIZE INTERNALDATE BODY.PEEK[HEADER])")
        part = next((v for v in data if isinstance(v, tuple)), None)
        if part is None:
            raise ValueError("QQ returned no message header")
        size = re.search(rb"RFC822.SIZE (\d+)", part[0])
        # QQ can return "6-Oct" instead of the RFC's two-character day. The
        # stdlib parser returns None for that otherwise valid server timestamp.
        metadata = re.sub(rb'INTERNALDATE "([1-9])-', rb'INTERNALDATE "0\1-', part[0])
        stamp = imaplib.Internaldate2tuple(metadata)
        if size is None or stamp is None or len(part[1]) > 100_000:
            raise ValueError("Invalid or oversized mail header metadata")
        return part[1], int(size[1]), datetime.fromtimestamp(time.mktime(stamp), timezone.utc)

    def body(self, uid):
        # Partial fetch bounds bytes even if size metadata is incorrect.
        data = self._uid("fetch", str(uid), f"(BODY.PEEK[]<0.{MAX_MAIL_BYTES + 1}>)")
        raw = next((v[1] for v in data if isinstance(v, tuple)), None)
        if raw is None or len(raw) > MAX_MAIL_BYTES:
            raise ValueError("Email exceeds 25 MB or could not be read")
        return raw

    def smtp(self):
        smtp = smtplib.SMTP_SSL("smtp.qq.com", 465, context=ssl.create_default_context(), timeout=30)
        try:
            smtp.login(self.mailbox, self.secret)
        except Exception:
            smtp.close()
            raise
        return smtp

    def probe_smtp(self):
        with self.smtp() as smtp:
            code, _ = smtp.noop()
            if code != 250:
                raise ValueError("SMTP NOOP failed")

    def send(self, message, recipient):
        with self.smtp() as smtp:
            refused = smtp.send_message(message, from_addr=self.mailbox, to_addrs=[recipient])
            if refused:
                raise ValueError("SMTP recipient was refused")


class QQInbox:
    def __init__(self, service, connection, mailbox, allowed_senders=None, *, require_tag=True):
        self.service, self.connection = service, connection
        self.mailbox = normalize_sender("email", mailbox)
        self.allowed = None if allowed_senders is None else {normalize_sender("email", s) for s in allowed_senders}
        self.require_tag = require_tag
        if self.allowed is not None and (not self.allowed or self.mailbox in self.allowed):
            raise ValueError("Configure a separate allowed test sender")
        self.account = "qq:" + digest(self.mailbox)[:32]
        with service.store.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS qq_receipts(id TEXT PRIMARY KEY, account TEXT, message_id TEXT, "
                       "result TEXT, send_status TEXT, error TEXT, input_hash TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS qq_cursor(account TEXT, validity INTEGER, uid INTEGER, PRIMARY KEY(account,validity))")
            db.execute("CREATE TABLE IF NOT EXISTS qq_threads(account TEXT, message_id TEXT, thread TEXT, sender TEXT, "
                       "input_hash TEXT, PRIMARY KEY(account,message_id))")

    def poll(self, since, *, max_messages=5, send_replies=False):
        when = datetime.fromisoformat(since.replace("Z", "+00:00"))
        if when.tzinfo is None or not 1 <= max_messages <= 10:
            raise ValueError("since needs a timezone; max_messages must be 1-10")
        rows = []
        if send_replies:
            with self.service.store.connect() as db:
                pending = db.execute("SELECT * FROM qq_receipts WHERE account=? AND send_status='prepared' ORDER BY rowid LIMIT ?",
                                     (self.account, max_messages)).fetchall()
            rows.extend(self._send(r["id"], json.loads(r["result"]), True) for r in pending)
        with self.service.store.connect() as db:
            cursor = db.execute("SELECT uid FROM qq_cursor WHERE account=? AND validity=?",
                                (self.account, self.connection.uidvalidity)).fetchone()
        uids = self.connection.uids(when, cursor[0] if cursor else 0)
        scanned = 0
        for uid in uids:
            if len(rows) >= max_messages:
                break
            # Network failures preserve the cursor so the same message can be fetched again.
            raw_header, size, at = self.connection.header(uid)
            header = BytesParser(policy=policy.default).parsebytes(raw_header)
            scanned += 1
            if at >= when and (not self.require_tag or "[VisaTest]" in str(header.get("Subject", ""))):
                try:
                    senders = set(addresses(header, "From"))
                    if not senders & (SYSTEM_SENDERS | {self.mailbox}) and (self.allowed is None or senders & self.allowed):
                        if size > MAX_MAIL_BYTES:
                            raise ValueError("Email exceeds 25 MB")
                        rows.append(self.receive(self.connection.body(uid), at, send_replies=send_replies))
                except ValueError as exc:
                    rejection = {"uid": uid, "send_status": "rejected", "error": str(exc)}
                    key = digest([self.account, self.connection.uidvalidity, uid])
                    write_json(self.service.store.root / "qq-rejections" / (key + ".json"), rejection)
                    rows.append(rejection)
            with self.service.store.transaction() as db:
                db.execute("INSERT OR REPLACE INTO qq_cursor VALUES (?,?,?)", (self.account, self.connection.uidvalidity, uid))
        return {"messages": rows, "scanned": scanned, "limit_reached": scanned < len(uids) or len(uids) == 100}

    def receive(self, raw, at, *, send_replies=False):
        mail = parse_mail(raw, self.mailbox, self.allowed, require_tag=self.require_tag)
        identity = {k: v for k, v in mail.items() if k != "files"}
        identity["files"] = [(name, hashlib.sha256(data).hexdigest()) for name, data in mail["files"]]
        fingerprint = digest(identity)
        receipt_id = digest([self.account, mail["message_id"]])
        with self.service.store.transaction() as db:
            old = db.execute("SELECT * FROM qq_receipts WHERE id=?", (receipt_id,)).fetchone()
            if old and old["input_hash"] != fingerprint:
                raise ValueError("Message-ID reused with changed contents")
            # A reply can refer to either an inbound message or our outbound Message-ID.
            references = [mail["message_id"], *reversed(mail["references"])]
            known = [row for ref in references if (row := db.execute(
                "SELECT * FROM qq_threads WHERE account=? AND message_id=?", (self.account, ref)).fetchone())]
            if any(r["sender"] != mail["sender"] for r in known) or len({r["thread"] for r in known}) > 1:
                raise ValueError("Referenced thread belongs to another sender or conflicting sessions")
            own = next((r for r in known if r["message_id"] == mail["message_id"]), None)
            if own and own["input_hash"] != fingerprint:
                raise ValueError("Message-ID reused with changed contents")
            thread = known[0]["thread"] if known else receipt_id
            db.execute("INSERT OR IGNORE INTO qq_threads VALUES (?,?,?,?,?)",
                       (self.account, mail["message_id"], thread, mail["sender"], fingerprint))
        if old:
            return self._send(receipt_id, json.loads(old["result"]), send_replies)
        files = []
        for index, (name, content) in enumerate(mail["files"]):
            target = self.service.store.root / "qq-files" / receipt_id / f"{index}-{name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            files.append(target)
        incoming = Incoming(channel="email", account=self.account, thread=thread, sender=mail["sender"],
                            message_id=receipt_id, text=mail["text"], at=at)
        result = Inbox(self.service).receive_connector(incoming, files, provider="imap")
        result.update(mail_sender=mail["sender"], mail_subject=mail["subject"], mail_parent=mail["message_id"],
                      mail_reply_id=f"<visa-{receipt_id}@{self.mailbox.split('@')[1]}>", mail_thread=thread)
        status = "failed" if result.get("error") else "prepared"
        with self.service.store.transaction() as db:
            db.execute("INSERT OR IGNORE INTO qq_receipts VALUES (?,?,?,?,?,NULL,?)",
                       (receipt_id, self.account, mail["message_id"], json.dumps(result, ensure_ascii=False), status, fingerprint))
            db.execute("INSERT OR IGNORE INTO qq_threads VALUES (?,?,?,?,NULL)",
                       (self.account, result["mail_reply_id"], thread, mail["sender"]))
        write_json(self.service.store.root / "qq-previews" / (receipt_id + ".json"), result)
        return self._send(receipt_id, result, send_replies)

    def _send(self, receipt_id, result, enabled):
        if result["mail_sender"] in SYSTEM_SENDERS:
            with self.service.store.transaction() as db:
                db.execute("UPDATE qq_receipts SET send_status='ignored',error='Provider notification' WHERE id=? AND send_status='prepared'",
                           (receipt_id,))
                status = db.execute("SELECT send_status FROM qq_receipts WHERE id=?", (receipt_id,)).fetchone()[0]
            return {"result": result, "send_status": status}
        def send():
            message = EmailMessage()
            message["From"], message["To"] = self.mailbox, result["mail_sender"]
            message["Subject"] = "Re: " + result["mail_subject"].removeprefix("Re: ")
            message["Message-ID"], message["In-Reply-To"] = result["mail_reply_id"], result["mail_parent"]
            message["References"] = result["mail_parent"]
            message["Date"] = format_datetime(datetime.now(timezone.utc))
            message["Auto-Submitted"] = "auto-replied"
            message.set_content(result["reply"])
            self.connection.send(message, result["mail_sender"])
            (self.service.store.root / "qq-previews" / (receipt_id + ".sent.eml")).write_bytes(message.as_bytes())
        allowed = self.allowed if self.allowed is not None else {result["mail_sender"]}
        return send_prepared_reply(self.service.store, "qq_receipts", receipt_id, result, enabled, allowed, send)


def receive_once(args, config, secret, budget):
    with QQConnection(config["mailbox"], secret) as connection:
        if args.action == "probe":
            connection.probe_smtp()
            return {"imap_login": True, "smtp_login": True, "sent": 0}
        service = VisaService(args.data, "live", hitl=args.hitl, budget=budget)
        allowed = None if config.get("accept_all") else config["allowed_senders"]
        result = QQInbox(service, connection, config["mailbox"], allowed,
                         require_tag=config.get("require_tag", True)).poll(
            args.since or config["since"], max_messages=args.max_messages, send_replies=args.send_replies)
        result["model_requests"] = budget.count()
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["probe", "poll", "watch", "stop"])
    parser.add_argument("--data", type=Path, default=Path("data/qq-test"))
    parser.add_argument("--hitl", choices=["on", "off"], default="off")
    parser.add_argument("--since")
    parser.add_argument("--max-messages", type=int, default=5)
    parser.add_argument("--request-cap", type=int, default=12)
    parser.add_argument("--send-replies", action="store_true")
    parser.add_argument("--interval", type=int, default=15, help="Polling interval for watch, minimum 10 seconds")
    args = parser.parse_args()
    if args.interval < 10 or args.request_cap < 1:
        parser.error("interval must be >=10 seconds and request-cap must be positive")
    stage = "local_configuration"
    try:
        stop_file = args.data / "qq-stop"
        if args.action == "stop":
            stop_file.touch()
            print("Stop requested; current event may finish before the worker exits")
            return
        config = json.loads((args.data / "qq-config.json").read_text(encoding="utf-8"))
        secret = build_encrypted_persistence(str(args.data / "qq-auth.bin")).load()
        budget = LiveBudget(args.data / "live-budget.sqlite3", args.request_cap)
        failures = 0
        if args.action == "watch":
            stop_file.unlink(missing_ok=True)
        while True:
            if args.action == "watch" and stop_file.exists():
                print("Mail worker stopped", flush=True)
                break
            if args.action != "probe" and budget.count() >= budget.limit:
                result = {"paused": "model_request_budget", "model_requests": budget.count(), "limit": budget.limit}
                write_json(args.data / "qq-watch-last.json", result)
                print(json.dumps(result), flush=True)
                break
            stage = "mail_connection_or_processing"
            try:
                result = receive_once(args, config, secret, budget)
                failures = 0
            except (OSError, imaplib.IMAP4.abort) as exc:
                failures += 1
                if args.action != "watch" or failures >= 3:
                    raise
                result = {"error_type": type(exc).__name__, "network_failures": failures,
                          "retry_after_seconds": args.interval, "model_requests": budget.count()}
            result["at"] = datetime.now(timezone.utc).isoformat()
            write_json(args.data / ("qq-" + args.action + "-last.json"), result)
            if args.action != "watch" or result.get("messages") or result.get("error_type"):
                print(json.dumps(result, ensure_ascii=False), flush=True)
            if args.action != "watch":
                break
            time.sleep(args.interval)
    except Exception as exc:
        # No traceback/provider error payload can expose authorization credentials.
        print(json.dumps({"error_type": type(exc).__name__, "stage": stage,
                          "smtp_code": getattr(exc, "smtp_code", None),
                          "error": "QQ operation failed; check local configuration, authorization and network. Sending is never retried automatically."}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
