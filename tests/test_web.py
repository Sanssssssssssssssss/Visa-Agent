import base64
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import threading

import pytest

from visa_agent.web import LocalApp, make_server

MATERIALS = Path(__file__).resolve().parents[1] / "datasets/materials/dev_visitor"


@pytest.fixture
def web(tmp_path):
    app = LocalApp(tmp_path, "offline", sample="visitor")
    server = make_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield app, server.server_port
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def request(web, path, body=None, *, authorized=True):
    app, port = web
    headers = {}
    if authorized:
        headers = {"X-Visa-Session": app.token, "Origin": f"http://127.0.0.1:{port}",
                   "Content-Type": "application/json", "Cookie": f"visa_workspace={app.workspace_id}"}
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        connection.request("GET" if body is None else "POST", path,
                           None if body is None else json.dumps({"case_id": app.case_id, **body}), headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_web_upload_review_and_retry_after_lost_response(web):
    files = [{"name": name, "content": base64.b64encode((MATERIALS / name).read_bytes()).decode()}
             for name in ("identity.pdf", "funds.pdf", "work.pdf")]
    body = {"event_id": "drop-1", "files": files}
    status, raw = request(web, "/api/event", body)
    case = json.loads(raw)["case"]
    assert status == 200 and case["status"] == "READY_FOR_REVIEW", raw
    assert len(case["documents"]) == 3 and not case["approval"]
    status, raw = request(web, "/api/event", body)
    duplicate = json.loads(raw)
    assert status == 200 and duplicate["result"]["duplicate"]
    assert duplicate["case"]["version"] == case["version"]
    assert request(web, "/pack/report.html")[0] == 200
    assert request(web, "/pack/../../cases.sqlite3")[0] == 400
    status, raw = request(web, "/api/review", {"version": case["version"], "notes": "Synthetic web test review"})
    assert status == 200 and json.loads(raw)["case"]["status"] == "COMPLETE"
    assert request(web, "/pack/download")[1].startswith(b"PK")


def test_default_blank_does_not_inject_demo_background(tmp_path):
    app = LocalApp(tmp_path, "offline")
    assert app.sample == "blank" and app.initial_text == ""
    state = app.event({"event_id": "own-input", "text": "route: student"})
    assert state["case"]["history"][0]["text"] == "route: student"
    assert [(f["key"], f["value"]) for f in state["case"]["facts"]] == [("route", "student")]


def test_web_rejects_cross_origin_and_bad_upload_names(web):
    assert request(web, "/api/new", {"sample": "blank"}, authorized=False)[0] == 403
    status, _ = request(web, "/api/event", {"files": [{"name": "../escape.pdf", "content": ""}]})
    assert status == 400
    assert not web[0].service.store.get(web[0].case_id).documents
    assert request(web, "/api/event", {"files": [{}] * 6})[0] == 400


def test_web_approval_cannot_skip_material_checks(web):
    status, _ = request(web, "/api/review", {"version": 0, "notes": "Should be rejected"})
    assert status == 400
    assert web[0].service.store.get(web[0].case_id).approval is None


def test_concurrent_redelivery_only_processes_event_once(web):
    body = {"event_id": "concurrent-upload", "files": [{
        "name": "identity.pdf",
        "content": base64.b64encode((MATERIALS / "identity.pdf").read_bytes()).decode(),
    }]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: request(web, "/api/event", body), range(12)))
    assert all(status == 200 for status, _ in responses)
    results = [json.loads(raw) for _, raw in responses]
    assert sum(not r["result"]["duplicate"] for r in results) == 1
    assert {r["case"]["version"] for r in results} == {1}
    app = web[0]
    assert len(app.service.store.get(app.case_id).documents) == 1
    assert len([t for t in app.service.store.traces(app.case_id) if not t.get("command")]) == 1


def test_browser_cookie_isolation_and_rehydration(web):
    app, port = web
    connection = http.client.HTTPConnection("127.0.0.1", port)
    connection.request("GET", "/")
    response = connection.getresponse()
    cookie = response.getheader("Set-Cookie").split(";", 1)[0]
    response.read()
    connection.request("GET", "/api/state", headers={"Cookie": cookie})
    response = connection.getresponse()
    other = json.loads(response.read())
    assert other["case"]["id"] != app.case_id
    connection.request("GET", "/api/state")
    assert connection.getresponse().status == 400
    connection.close()
    restored = LocalApp(app.service.store.root, "offline", workspace_id=app.workspace_id)
    assert restored.case_id == app.case_id and restored.session_id == app.session_id


def test_web_exit_reset_and_channel_switch_do_not_reuse_facts(tmp_path):
    app = LocalApp(tmp_path, "offline")
    first = app.event({"event_id": "first", "text": "applicant_name: Old Name"})["case"]["id"]
    exited = app.event({"event_id": "exit", "text": "/exit"})
    assert exited["session"]["state"] == "closed"
    fresh = app.event({"event_id": "reset", "text": "/reset"})
    assert fresh["case"]["id"] != first and not fresh["case"]["facts"]
    app.connect_identity({"channel": "email", "sender": "a@example.com", "thread": "mail-a"})
    app.event({"event_id": "mail-first", "text": "applicant_name: Mail A"})
    a = app.case_id
    app.connect_identity({"channel": "email", "sender": "b@example.com", "thread": "mail-b"})
    assert not app.service.store.get(app.case_id).facts
    app.connect_identity({"channel": "email", "sender": "a@example.com", "thread": "mail-a"})
    assert app.case_id == a and app.service.store.get(a).facts[0].value == "Mail A"
    with pytest.raises(ValueError, match="绑定其他发件人"):
        app.connect_identity({"channel": "email", "sender": "b@example.com", "thread": "mail-a"})


def test_reset_in_another_workspace_rejects_stale_tab_input(web):
    first, port = web
    routing = {"channel": "email", "sender": "same@example.com", "thread": "shared"}
    first.connect_identity(routing)
    other = LocalApp(first.service.store.root, "offline")
    other.connect_identity(routing)
    stale_id = first.case_id
    other.event({"event_id": "reset-other", "text": "/reset"})
    status, _ = request((first, port), "/api/event", {"case_id": stale_id, "event_id": "stale", "text": "age: 99"})
    assert status == 409
    assert first.case_id == other.case_id and first.case_id != stale_id
    assert not first.service.store.get(first.case_id).facts
