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
    app = LocalApp(tmp_path, "offline")
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
                   "Content-Type": "application/json"}
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
    assert len(app.service.store.traces(app.case_id)) == 1
