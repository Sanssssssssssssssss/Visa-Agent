"""Local drag-and-drop UI over the existing service. No additional dependencies."""

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import unquote, urlsplit
import uuid

from .documents import MAX_BYTES
from .service import VisaService
from .types import CaseEvent

ROOT = Path(__file__).resolve().parents[2]
MAX_REQUEST_BYTES = 70 * 1024 * 1024
SAMPLES = {"visitor": "dev_visitor", "student": "dev_student", "skilled_worker": "dev_skilled_worker"}


class LocalApp:
    def __init__(self, root="data", mode="live", *, sample="blank"):
        self.service = VisaService(root, mode)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.new_case(sample)

    def new_case(self, sample):
        if sample not in {*SAMPLES, "blank"}:
            raise ValueError("Unknown sample")
        self.sample = sample
        self.initial_text = ""
        if sample != "blank":
            scenario = json.loads((ROOT / "datasets/cases" / (SAMPLES[sample] + ".json")).read_text(encoding="utf-8"))
            self.initial_text = scenario["events"][0]["text"]
        self.case_id = "web-" + uuid.uuid4().hex[:16]
        self.service.store.create(self.case_id)
        self.initial_sent = False
        self.event_prefixes = {}
        self.last_error = None

    def state(self):
        case = self.service.store.get(self.case_id)
        return {"case": case.model_dump(mode="json"), "sample": self.sample,
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
        prefix = self.event_prefixes.setdefault(event_id, self.initial_text if not self.initial_sent else "")
        text = prefix + ("\n" if prefix else "") + text
        result = self.service.handle_event(CaseEvent(case_id=self.case_id, event_id=event_id,
            kind="upload" if paths else "message", text=text, attachments=paths))
        self.last_error = result.error
        # On failure the same initial context must be retained for an exact retry.
        if not result.error:
            self.initial_sent = True
        return {**self.state(), "result": result.model_dump(mode="json")}


def make_server(app, port=8765):
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
            if download:
                self.send_header("Content-Disposition", 'attachment; filename="visa-materials.zip"')
            self.end_headers()
            self.wfile.write(content)

        def trusted_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.trusted_host():
                return self.send(403, {"error": "Local access only"})
            path = unquote(urlsplit(self.path).path)
            try:
                if path == "/":
                    html = Path(__file__).with_name("web.html").read_text(encoding="utf-8")
                    return self.send(200, html.replace("__SESSION_TOKEN__", app.token).encode(), "text/html; charset=utf-8")
                if path == "/api/state":
                    return self.send(200, app.state())
                if path == "/api/trace":
                    return self.send(200, app.service.store.traces(app.case_id))
                if path.startswith("/pack/"):
                    case = app.service.store.get(app.case_id)
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
            if (not self.trusted_host() or self.headers.get("Origin") != origin
                    or not secrets.compare_digest(self.headers.get("X-Visa-Session", ""), app.token)):
                return self.send(403, {"error": "请在本地页面操作，或刷新页面后重试。"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    return self.send(413, {"error": "上传内容过大，请拆分。"})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Expected an object")
                with app.lock:
                    if body.get("case_id") != app.case_id:
                        return self.send(409, {"error": "案件已切换，请刷新页面。"})
                    if self.path == "/api/new":
                        app.new_case(body.get("sample", "blank"))
                        result = app.state()
                    elif self.path == "/api/event":
                        result = app.event(body)
                    elif self.path == "/api/review":
                        app.service.review_case(app.case_id, body["version"], "approve", body["notes"],
                                                reviewer="browser-tester")
                        result = app.state()
                    else:
                        return self.send(404, {"error": "Not found"})
                    self.send(200, result)
            except (ValueError, TypeError, KeyError, OSError) as exc:
                self.send(400, {"error": str(exc)})

    # ponytail: one browser workspace per process; add sessions only for a multi-user service.
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Local visa material upload page")
    parser.add_argument("--data", default="data")
    parser.add_argument("--mode", choices=["live", "offline"], default="live")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--sample", choices=[*SAMPLES, "blank"], default="blank")
    args = parser.parse_args()
    server = make_server(LocalApp(args.data, args.mode, sample=args.sample), args.port)
    print(f"Visa Agent: http://127.0.0.1:{server.server_port} ({args.mode})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
