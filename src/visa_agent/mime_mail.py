"""Read MIME messages without loading remote content; keep quoted history out."""
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser
from pathlib import Path
import re

from .documents import MAX_BYTES
from .inbox import normalize_sender

MAX_MAIL_BYTES = 25 * 1024 * 1024
MESSAGE_ID = re.compile(r"<[^<>\s@]+@[^<>\s@]+>")
# Observed QQ provider notification account. This is not a general spam detector.
SYSTEM_SENDERS = {"10000@qq.com"}


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.finished = [], [], False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id", "").lower() == "divrplyfwdmsg":
            self.finished = True  # Outlook's previous-message header and following content.
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.append(tag)
            return
        if tag in {"script", "style", "blockquote"} or "gmail_quote" in attrs.get("class", ""):
            self.skip.append(tag)
        elif tag in {"p", "div", "br", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.skip and tag == self.skip[-1]:
            self.skip.pop()
        elif not self.skip and tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip and not self.finished:
            self.parts.append(data)


def new_body(message):
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        parser = HTMLText()
        parser.feed(text)
        text = "".join(parser.parts)
    lines = []
    for line in text.splitlines():
        if (line.lstrip().startswith(">") or
            re.match(r"^\s*(?:On .+wrote:|在.+写道[：:]|[-_]{2,}\s*(?:Original Message|原始邮件))", line, re.I) or
            (lines and re.match(r"^\s*(?:From:|发件人[：:])", line, re.I))):
            break
        lines.append(line)
    # Outlook's plain-text alternative leaves an underline before its From
    # header. Remove that quote separator too so a standalone /reset stays a
    # command instead of becoming a new model message.
    while lines and (not lines[-1].strip() or re.fullmatch(r"[-_]{5,}", lines[-1].strip())):
        lines.pop()
    result = "\n".join(lines).strip()
    if len(result) > 12000:
        raise ValueError("Email text exceeds 12000 characters; split the message")
    return result


def addresses(message, key):
    values = message.get_all(key, [])
    if key.lower() in {"from", "sender", "reply-to"} and len(values) > 1:
        raise ValueError("Duplicate identity headers")
    return [normalize_sender("email", address) for _, address in getaddresses([str(v) for v in values])]


def parse_mail(raw, mailbox, allowed, *, require_tag=True):
    if len(raw) > MAX_MAIL_BYTES:
        raise ValueError("Email exceeds 25 MB")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if message.defects:
        raise ValueError("Malformed MIME message")
    senders = addresses(message, "From")
    if (len(senders) != 1 or senders[0] == mailbox or senders[0] in SYSTEM_SENDERS or
        (allowed is not None and senders[0] not in allowed) or mailbox not in addresses(message, "To")):
        raise ValueError("Test sender or recipient mismatch")
    sender = senders[0]
    if addresses(message, "Sender") not in ([], [sender]) or addresses(message, "Reply-To") not in ([], [sender]):
        raise ValueError("Sender or Reply-To differs from the allowed sender")
    subject = str(message.get("Subject", ""))
    if ((require_tag and "[VisaTest]" not in subject) or
        str(message.get("Auto-Submitted", "no")).lower() != "no" or message.get("List-ID") or
        str(message.get("Precedence", "")).lower() in {"bulk", "list", "junk"}):
        raise ValueError("Only tagged, non-automated test messages are processed")
    ids = message.get_all("Message-ID", [])
    message_id = str(ids[0]).strip() if len(ids) == 1 else ""
    if not MESSAGE_ID.fullmatch(message_id) or len(message_id) > 998 or not message_id.isascii():
        raise ValueError("A valid unique Message-ID is required")
    references = MESSAGE_ID.findall(str(message.get("References", "")) + " " + str(message.get("In-Reply-To", "")))
    if len(references) > 100:
        raise ValueError("Email reference chain is too long")
    files = []
    for part in message.walk():
        if part.get_content_disposition() == "inline":
            continue  # Signature logos are not evidence; photos must be attached as files.
        if part.get_content_type() == "message/rfc822":
            raise ValueError("Attached emails are unsupported; send original PDF or images")
        if part.get_content_disposition() == "attachment" or part.get_filename():
            name = part.get_filename() or "unnamed"
            if part.is_multipart() or part.get_content_type() == "message/rfc822":
                raise ValueError("Attached emails are unsupported; send original PDF or images")
            if any(c in name for c in '/\\<>:"|?*') or any(ord(c) < 32 for c in name) or len(name) > 180:
                raise ValueError("Unsafe attachment filename")
            if Path(name).suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
                raise ValueError("Unsupported attachment type")
            content = part.get_payload(decode=True)
            if content is None or len(content) > MAX_BYTES or part.defects:
                raise ValueError("Unreadable or oversized attachment")
            files.append((name, content))
    if len(files) > 5:
        raise ValueError("Too many attachments; split the email")
    text = new_body(message)
    if not text and not files:
        raise ValueError("No new text or supported attachment found")
    return {"message_id": message_id, "sender": sender, "subject": subject,
            "references": references, "text": text, "files": files}
