"""Bounded Graph inbox polling, file attachments, and persisted reply receipts.

This pilot reads only tagged mail from configured test senders. Mailbox OAuth
does not authenticate an arbitrary internet From header or establish identity.
"""
import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .documents import MAX_BYTES
from .inbox import Inbox, Incoming, normalize_sender
from .mail_outbox import send_prepared_reply
from .service import VisaService
from .store import digest, write_json

GRAPH = "https://graph.microsoft.com/v1.0"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Unexpected Graph redirect")


class GraphClient:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, body=None, *, max_bytes=15_000_000):
        url = path if path.startswith("https://") else GRAPH + path
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com" or not parsed.path.startswith("/v1.0/"):
            raise ValueError("Unexpected Graph pagination URL")
        headers = {"Authorization": "Bearer " + self.token(), "Content-Type": "application/json",
                   "Prefer": 'IdType="ImmutableId", outlook.body-content-type="text"'}
        request = Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
        # Sending has no automatic retry: after a connection failure, delivery may
        # already have happened. The persistent receipt handles that ambiguity.
        with build_opener(NoRedirect()).open(request, timeout=45) as response:
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ValueError("Graph response exceeds input limit")
            return json.loads(raw) if raw else {}


class OutlookInbox:
    def __init__(self, service, graph, mailbox, allowed_senders):
        self.service, self.graph = service, graph
        self.mailbox = normalize_sender("email", mailbox)
        self.allowed = {normalize_sender("email", s) for s in allowed_senders}
        if not self.allowed or self.mailbox in self.allowed:
            raise ValueError("Configure at least one separate test sender; do not allow the agent mailbox itself")
        with service.store.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS outlook_receipts("
                       "id TEXT PRIMARY KEY, account TEXT, message_id TEXT, result TEXT, send_status TEXT, error TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS outlook_cursor(account TEXT PRIMARY KEY, received_at TEXT)")

    def poll(self, since, *, max_messages=5, send_replies=False):
        when = datetime.fromisoformat(since.replace("Z", "+00:00"))
        if when.tzinfo is None or not 1 <= max_messages <= 10:
            raise ValueError("since needs a timezone; max_messages must be 1-10")
        profile = self.graph.request("GET", "/me?$select=id,mail,userPrincipalName")
        addresses = {normalize_sender("email", profile[k]) for k in ("mail", "userPrincipalName") if profile.get(k)}
        if self.mailbox not in addresses:
            raise ValueError("Signed-in Microsoft mailbox does not match VISA_OUTLOOK_MAILBOX")
        account = "outlook:" + profile["id"]
        results = []
        if send_replies:
            with self.service.store.connect() as db:
                pending = db.execute("SELECT * FROM outlook_receipts WHERE account=? AND send_status='prepared' ORDER BY rowid LIMIT ?",
                                     (account, max_messages)).fetchall()
            for row in pending:
                results.append(self._send(row["id"], row["message_id"], json.loads(row["result"]), True))
        if len(results) >= max_messages:
            return {"messages": results, "scanned": 0, "limit_reached": True}
        with self.service.store.connect() as db:
            cursor = db.execute("SELECT received_at FROM outlook_cursor WHERE account=?", (account,)).fetchone()
        if cursor:
            when = max(when, datetime.fromisoformat(cursor[0].replace("Z", "+00:00")))
        query = urlencode({"$filter": f"receivedDateTime ge {when.isoformat()}",
                           "$orderby": "receivedDateTime asc", "$top": 20, "$select": "id,subject,from,receivedDateTime"})
        page, scanned = "/me/mailFolders/inbox/messages?" + query, 0
        for _ in range(5):  # Bounded scan even when the inbox contains unrelated mail.
            listing = self.graph.request("GET", page)
            for item in listing.get("value", []):
                scanned += 1
                receipt_id = digest([account, item["id"]])
                with self.service.store.connect() as db:
                    seen = db.execute("SELECT 1 FROM outlook_receipts WHERE id=?", (receipt_id,)).fetchone()
                if not seen and "[VisaTest]" in item.get("subject", ""):
                    sender = item.get("from", {}).get("emailAddress", {}).get("address", "")
                    try:
                        if sender and normalize_sender("email", sender) in self.allowed:
                            results.append(self.receive(account, item["id"], send_replies=send_replies))
                    except ValueError as exc:
                        rejection = {"message_id": item["id"], "error": str(exc), "send_status": "rejected"}
                        with self.service.store.transaction() as db:
                            db.execute("INSERT OR IGNORE INTO outlook_receipts VALUES (?,?,?,?,?,?)",
                                       (receipt_id, account, item["id"], json.dumps(rejection), "rejected", str(exc)))
                        results.append(rejection)
                with self.service.store.transaction() as db:
                    db.execute("INSERT OR REPLACE INTO outlook_cursor VALUES (?,?)", (account, item["receivedDateTime"]))
                if len(results) >= max_messages:
                    return {"messages": results, "scanned": scanned, "limit_reached": True}
            page = listing.get("@odata.nextLink")
            if not page:
                break
        return {"messages": results, "scanned": scanned, "limit_reached": bool(page)}

    def receive(self, account, message_id, *, send_replies=False):
        receipt_id = digest([account, message_id])
        with self.service.store.connect() as db:
            old = db.execute("SELECT * FROM outlook_receipts WHERE id=?", (receipt_id,)).fetchone()
        if old:
            result = json.loads(old["result"])
            return self._send(receipt_id, message_id, result, send_replies)
        path = "/me/messages/" + quote(message_id, safe="")
        fields = "id,conversationId,subject,from,sender,replyTo,toRecipients,uniqueBody,receivedDateTime,hasAttachments,internetMessageHeaders"
        message = self.graph.request("GET", path + "?$select=" + fields)
        sender = normalize_sender("email", message["from"]["emailAddress"]["address"])
        actual_sender = normalize_sender("email", message.get("sender", message["from"])["emailAddress"]["address"])
        recipients = {normalize_sender("email", r["emailAddress"]["address"]) for r in message.get("toRecipients", [])}
        replies = {normalize_sender("email", r["emailAddress"]["address"]) for r in message.get("replyTo", [])}
        headers = {h["name"].lower(): h["value"].lower() for h in message.get("internetMessageHeaders", [])}
        if sender not in self.allowed or actual_sender != sender or self.mailbox not in recipients:
            raise ValueError("Test sender or recipient mismatch")
        if replies and replies != {sender}:
            raise ValueError("Reply-To differs from the allowed sender")
        if "[VisaTest]" not in message.get("subject", "") or headers.get("auto-submitted", "no") != "no" or "list-id" in headers:
            raise ValueError("Only tagged, non-automated test messages are processed")
        body = message.get("uniqueBody", {})
        if body.get("contentType", "").lower() != "text":
            raise ValueError("Graph did not return a plain-text uniqueBody")
        files = []
        if message.get("hasAttachments"):
            listing = self.graph.request("GET", path + "/attachments?$select=id,name,size,isInline")
            entries = [a for a in listing.get("value", []) if not a.get("isInline")]
            if listing.get("@odata.nextLink") or len(entries) > 5:
                raise ValueError("Too many attachments; split the email")
            for index, attachment in enumerate(entries):
                name = attachment["name"]
                if any(c in name for c in '/\\<>:"|?*') or any(ord(c) < 32 for c in name) or len(name) > 180:
                    raise ValueError("Unsafe attachment filename")
                suffix = Path(name).suffix.lower()
                if suffix not in {".pdf", ".png", ".jpg", ".jpeg"} or attachment["size"] > MAX_BYTES:
                    raise ValueError("Unsupported attachment type or size")
                data = self.graph.request("GET", path + "/attachments/" + quote(attachment["id"], safe=""))
                if data.get("@odata.type") != "#microsoft.graph.fileAttachment":
                    raise ValueError("Only file attachments are supported")
                raw = base64.b64decode(data["contentBytes"], validate=True)
                if len(raw) > MAX_BYTES:
                    raise ValueError("Attachment exceeds 10 MB")
                target = self.service.store.root / "outlook-files" / receipt_id / hashlib.sha256(raw).hexdigest() / f"{index}-{name}"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                files.append(target)
        incoming = Incoming(channel="email", account=account, thread=message["conversationId"], sender=sender,
                            message_id=message_id, text=body.get("content", ""),
                            at=datetime.fromisoformat(message["receivedDateTime"].replace("Z", "+00:00")))
        result = Inbox(self.service).receive_connector(incoming, files)
        result["mail_sender"] = sender
        status = "failed" if result.get("error") else "prepared"
        with self.service.store.transaction() as db:
            db.execute("INSERT OR IGNORE INTO outlook_receipts VALUES (?,?,?,?,?,NULL)",
                       (receipt_id, account, message_id, json.dumps(result, ensure_ascii=False), status))
        write_json(self.service.store.root / "outlook-previews" / (receipt_id + ".json"),
                   {"to": sender, "message_id": message_id, "result": result})
        return self._send(receipt_id, message_id, result, send_replies)

    def _send(self, receipt_id, message_id, result, enabled):
        def send():
            self.graph.request("POST", "/me/messages/" + quote(message_id, safe="") + "/reply",
                               {"message": {"body": {"contentType": "Text", "content": result["reply"]}}})
        return send_prepared_reply(self.service.store, "outlook_receipts", receipt_id, result,
                                   enabled, self.allowed, send)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["login", "poll"])
    parser.add_argument("--data", default="data/outlook-test")
    parser.add_argument("--hitl", choices=["on", "off"])
    parser.add_argument("--since", help="Only scan messages received since this ISO timestamp with timezone")
    parser.add_argument("--max-messages", type=int, default=5)
    parser.add_argument("--send-replies", action="store_true", help="Authorize sending to configured test senders")
    args = parser.parse_args()
    from .outlook_auth import OutlookAuth
    try:
        auth = OutlookAuth(Path(args.data), send_replies=args.send_replies)
        if args.action == "login":
            result = auth.login()
        else:
            if not args.since:
                parser.error("poll requires --since")
            service = VisaService(args.data, "live", hitl=args.hitl)
            adapter = OutlookInbox(service, GraphClient(auth.token), auth.mailbox,
                                   [s.strip() for s in os.getenv("VISA_OUTLOOK_ALLOW_SENDERS", "").split(",") if s.strip()])
            result = adapter.poll(args.since, max_messages=args.max_messages, send_replies=args.send_replies)
        print(json.dumps(result, ensure_ascii=False, default=str))
    except Exception as exc:
        # Provider error bodies and token cache internals are not written to logs.
        print(json.dumps({"error_type": type(exc).__name__, "error": str(exc) if isinstance(exc, ValueError) else "Outlook operation failed; no automatic send retry"}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
