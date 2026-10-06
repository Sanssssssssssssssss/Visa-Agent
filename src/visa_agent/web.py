"""Local drag-and-drop UI over the existing service. No additional dependencies."""

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, unquote, urlsplit
import uuid

from .documents import MAX_BYTES
from .conversation import material_progress, action_for
from .diagnostics import document_issues
from .service import VisaService
from .inbox import Inbox, Incoming, normalize_sender
from .evidence import Evidence
from .types import CaseEvent

ROOT = Path(os.getenv("VISA_PROJECT_ROOT", str(Path(__file__).resolve().parents[2])))
MAX_REQUEST_BYTES = 70 * 1024 * 1024
SAMPLES = {"visitor": "dev_visitor", "student": "dev_student", "skilled_worker": "dev_skilled_worker"}


class LocalApp:
    def __init__(self, root="data", mode="live", *, sample="blank", workspace_id=None, hitl=None):
        self.service = VisaService(root, mode, hitl=hitl)
        self.workspace_id = workspace_id or secrets.token_hex(32)
        self.token = self.workspace_id
        self.inbox = Inbox(self.service)
        self.lock = threading.Lock()
        self.last_notice = ""
        with self.service.store.connect() as db:
            prior = db.execute("SELECT body FROM web_workspaces WHERE id=?", (self.workspace_id,)).fetchone()
        if prior:
            self.__dict__.update(json.loads(prior[0]))
            self.case_id = self.inbox.session(self.session_id)["case_id"]
            return
        self.channel, self.account, self.sender = "web", "local-web", self.workspace_id
        self.external_thread = uuid.uuid4().hex
        self.new_case(sample)

    def save_workspace(self):
        fields = ("sample", "initial_text", "initial_sent", "event_prefixes", "last_error", "case_id",
                  "channel", "account", "sender", "external_thread", "session_id", "last_notice")
        with self.service.store.transaction() as db:
            db.execute("INSERT OR REPLACE INTO web_workspaces VALUES (?,?)", (self.workspace_id,
                json.dumps({k: getattr(self, k) for k in fields}, ensure_ascii=False)))

    def new_case(self, sample, *, routing=None):
        if sample not in {*SAMPLES, "blank", "visitor_zh"}:
            raise ValueError("Unknown sample")
        if routing:
            channel = routing.get("channel", "web")
            if channel not in {"web", "email", "whatsapp"}:
                raise ValueError("Unknown channel")
            sender = self.workspace_id if channel == "web" else normalize_sender(channel, routing.get("sender", ""))
            # These are explicitly simulated operator identities, not authenticated customers.
            self.channel, self.account, self.sender = channel, "local-" + channel, sender
            self.external_thread = routing.get("thread") or uuid.uuid4().hex
        incoming = Incoming(channel=self.channel, account=self.account, sender=self.sender,
                            thread=self.external_thread, message_id=uuid.uuid4().hex, text="/start")
        result = self.inbox.receive_simulated(incoming, test_mode=sample != "blank")
        self.case_id, self.session_id = result["case_id"], result["session_id"]
        self.sample, self.initial_text = sample, ""
        if sample in SAMPLES:
            scenario = json.loads((ROOT / "datasets/cases" / (SAMPLES[sample] + ".json")).read_text(encoding="utf-8"))
            self.initial_text = scenario["events"][0]["text"]
        self.initial_sent = False
        self.event_prefixes = {}
        self.last_error = None
        self.last_notice = result["reply"]
        self.save_workspace()

    def connect_identity(self, routing):
        from .store import digest
        channel = routing.get("channel", "web")
        sender = self.workspace_id if channel == "web" else normalize_sender(channel, routing.get("sender", ""))
        incoming = Incoming(channel=channel, account="local-" + channel, sender=sender,
                            thread=routing.get("thread") or uuid.uuid4().hex, message_id=uuid.uuid4().hex)
        sid = digest([incoming.channel, incoming.account, incoming.thread])
        with self.service.store.connect() as db:
            row = db.execute("SELECT * FROM inbox_sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            return self.new_case("blank", routing=routing)
        if row["sender"] != sender:
            raise ValueError("该外部会话已绑定其他发件人，不能读取或覆盖。")
        self.channel, self.account, self.sender = channel, incoming.account, sender
        self.external_thread, self.session_id, self.case_id = incoming.thread, sid, row["case_id"]
        case = self.service.store.get(self.case_id)
        self.sample = "visitor_zh" if case.test_mode else "blank"
        self.initial_text, self.event_prefixes, self.last_error = "", {}, None
        self.initial_sent = bool(case.history_count)
        self.last_notice = "已恢复此发件人的会话。"
        self.save_workspace()

    def sync_case(self):
        """Another local workspace may reset the same simulated conversation."""
        active_id = self.inbox.session(self.session_id)["case_id"]
        if active_id != self.case_id:
            self.case_id = active_id
            case = self.service.store.get(active_id)
            self.sample = "visitor_zh" if case.test_mode else "blank"
            self.initial_text, self.event_prefixes, self.last_error = "", {}, None
            self.initial_sent = bool(case.history_count)
            self.last_notice = "会话已在另一页面重置，已切换到当前案件。"
            self.save_workspace()

    def state(self):
        self.sync_case()
        case = self.service.store.get(self.case_id)
        evidence = Evidence(case)
        material_states = {d.id: {
            "saved": True, "readable": bool(d.pages) and not d.problems,
            "usable_for_checks": evidence.admissible(d), "field_count": sum(f.source_id == d.id for f in case.facts),
            "adviser_approved": case.approval is not None,
        } for d in case.documents}
        return {"case": case.model_dump(mode="json"), "sample": self.sample,
                "session": self.inbox.session(self.session_id), "material_states": material_states,
                "notice": self.last_notice,
                "progress": material_progress(case),
                "customer_issues": list(dict.fromkeys(action_for(c, case)[1] for c in case.checks
                                                       if c.status in {"fail", "unknown"})),
                "diagnostics": [i for d in case.documents for i in document_issues(d)],
                "initial_text": self.initial_text, "mode": self.service.mode,
                "used": self.service.budget.count(), "limit": self.service.budget.limit,
                "key_available": bool(os.getenv("VISA_API_KEY") or os.getenv("DEEPSEEK_API_KEY")),
                "error": self.last_error}

    def event(self, body):
        files = body.get("files", [])
        text = body.get("text", "")
        if not isinstance(files, list) or len(files) > 5:
            raise ValueError("每次最多上传 5 个文件。")
        if not isinstance(text, str) or len(text) > 12000:
            raise ValueError("消息过长，请拆分发送。")
        if not files and not text.strip():
            raise ValueError("请上传文件或填写消息。")
        event_id = body.get("event_id", uuid.uuid4().hex)
        CaseEvent(case_id=self.case_id, event_id=event_id)
        decoded = []
        for item in files:
            name = item["name"]
            if (not isinstance(name, str) or len(name) > 180 or "/" in name or "\\" in name
                    or any(c in name for c in '<>:"|?*\x00') or name.endswith((".", " "))):
                raise ValueError("文件名无效。")
            if Path(name).suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
                raise ValueError("仅支持 PDF、PNG、JPEG 文件。")
            data = base64.b64decode(item["content"], validate=True)
            if len(data) > MAX_BYTES:
                raise ValueError("单文件不能超过 10 MB。")
            decoded.append((name, data))
        paths = []
        for index, (name, data) in enumerate(decoded):
            path = self.service.store.root / "web-uploads" / self.case_id / event_id / str(index) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_bytes() != data:
                raise ValueError("同一事件 ID 的文件内容不能改变。")
            path.write_bytes(data)
            paths.append(str(path))
        command = text.strip().lower() in {"/exit", "/reset", "/start", "/help", "/status"}
        prefix = self.event_prefixes.setdefault(event_id, self.initial_text if not self.initial_sent and not command else "")
        text = prefix + ("\n" if prefix else "") + text
        # Persist routing/prefix before processing so a restart retries identical content.
        self.save_workspace()
        result = self.inbox.receive_simulated(Incoming(channel=self.channel, account=self.account,
            thread=self.external_thread, sender=self.sender, message_id=event_id, text=text), paths)
        self.case_id = self.inbox.session(self.session_id)["case_id"]
        self.last_error = result.get("error")
        self.last_notice = result["reply"] if result.get("command") or result.get("session_state") == "closed" else ""
        # On failure the same initial context must be retained for an exact retry.
        if not result.get("error"):
            self.initial_sent = True
        if result.get("command") in {"/reset", "/start"} and not result.get("duplicate"):
            self.sample, self.initial_text, self.event_prefixes = "blank", "", {}
        self.save_workspace()
        return {**self.state(), "result": result}


def make_server(app, port=8765):
    workspaces = {app.workspace_id: app}
    workspace_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # The case service already records input, result and errors locally.

        def send(self, status, content, kind="application/json; charset=utf-8", download=False):
            if not isinstance(content, bytes):
                content = json.dumps(content, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if getattr(self, "new_cookie", None):
                self.send_header("Set-Cookie", f"visa_workspace={self.new_cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000")
            if download:
                self.send_header("Content-Disposition", 'attachment; filename="visa-materials.zip"')
            self.end_headers()
            self.wfile.write(content)

        def trusted_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def workspace(self, *, create=False):
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie.get("visa_workspace")
            token = token.value if token else ""
            with workspace_lock:
                if token in workspaces:
                    return workspaces[token]
                with app.service.store.connect() as db:
                    exists = db.execute("SELECT 1 FROM web_workspaces WHERE id=?", (token,)).fetchone()
                if exists:
                    current = LocalApp(app.service.store.root, app.service.mode, workspace_id=token, hitl=app.service.hitl_enabled)
                elif create:
                    current = LocalApp(app.service.store.root, app.service.mode, sample=app.sample, hitl=app.service.hitl_enabled)
                    self.new_cookie = current.workspace_id
                else:
                    raise ValueError("请打开本地首页建立会话。")
                workspaces[current.workspace_id] = current
                return current

        def do_GET(self):
            if not self.trusted_host():
                return self.send(403, {"error": "Local access only"})
            path = unquote(urlsplit(self.path).path)
            try:
                current = self.workspace(create=path == "/")
                if path == "/":
                    html = Path(__file__).with_name("web.html").read_text(encoding="utf-8")
                    return self.send(200, html.replace("__SESSION_TOKEN__", current.token).encode(), "text/html; charset=utf-8")
                if path == "/api/state":
                    return self.send(200, current.state())
                if path == "/api/trace":
                    return self.send(200, current.service.store.traces(current.case_id))
                if path == "/api/history":
                    before = parse_qs(urlsplit(self.path).query).get("before", [None])[0]
                    return self.send(200, current.service.store.dialogue(current.case_id,
                                     before=int(before) if before else None))
                if path.startswith("/pack/"):
                    case = current.service.store.get(current.case_id)
                    if not case.pack_path:
                        raise ValueError("材料包尚未生成。")
                    archive = Path(case.pack_path)
                    if path == "/pack/download":
                        return self.send(200, archive.read_bytes(), "application/zip", download=True)
                    directory = archive.with_suffix("").resolve()
                    target = (directory / path.removeprefix("/pack/")).resolve()
                    if not target.is_relative_to(directory) or not target.is_file():
                        raise ValueError("Unknown pack file")
                    return self.send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                self.send(404, {"error": "Not found"})
            except (ValueError, OSError) as exc:
                self.send(400, {"error": str(exc)})

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            try:
                current = self.workspace()
            except ValueError:
                return self.send(403, {"error": "请先打开首页建立会话。"})
            if (not self.trusted_host() or self.headers.get("Origin") != origin
                    or not secrets.compare_digest(self.headers.get("X-Visa-Session", ""), current.token)):
                return self.send(403, {"error": "请在本地页面操作，或刷新页面后重试。"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    return self.send(413, {"error": "上传内容过大，请拆分。"})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Expected an object")
                with current.lock:
                    current.sync_case()
                    if body.get("case_id") != current.case_id:
                        from .store import digest
                        key = digest([current.channel, current.account, body.get("event_id")])
                        with current.service.store.connect() as db:
                            old = db.execute("SELECT result FROM inbox_deliveries WHERE id=? AND session_id=?",
                                             (key, current.session_id)).fetchone()
                        if self.path != "/api/event" or not old or not old["result"]:
                            return self.send(409, {"error": "案件已切换，请刷新页面。"})
                    if self.path == "/api/new":
                        current.new_case(body.get("sample", "blank"), routing=body.get("routing"))
                        result = current.state()
                    elif self.path == "/api/event":
                        result = current.event(body)
                    elif self.path == "/api/connect":
                        current.connect_identity(body.get("routing", {}))
                        result = current.state()
                    elif self.path == "/api/review":
                        current.service.review_case(current.case_id, body["version"], "approve", body["notes"],
                                                reviewer="browser-tester")
                        result = current.state()
                    else:
                        return self.send(404, {"error": "Not found"})
                    self.send(200, result)
            except (ValueError, TypeError, KeyError, OSError) as exc:
                self.send(400, {"error": str(exc)})

    # Browser cookies select durable workspaces; business messages use channel identities.
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Local visa material upload page")
    parser.add_argument("--data", default="data")
    parser.add_argument("--mode", choices=["live", "offline"], default="live")
    parser.add_argument("--hitl", choices=["on", "off"], help="Policy for new cases; otherwise VISA_HITL or on")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--sample", choices=[*SAMPLES, "blank", "visitor_zh"], default="blank")
    args = parser.parse_args()
    server = make_server(LocalApp(args.data, args.mode, sample=args.sample, hitl=args.hitl), args.port)
    print(f"Visa Agent: http://127.0.0.1:{server.server_port} ({args.mode})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
