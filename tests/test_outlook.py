import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from visa_agent.outlook import GraphClient, NoRedirect, OutlookInbox
from visa_agent.service import VisaService


def mail(id="m1", sender_address="lin@example.com", thread="t1", **changes):
    def address(value):
        return {"emailAddress": {"address": value}}
    return {"id": id, "conversationId": thread, "subject": "[VisaTest] 准备材料", "from": address(sender_address),
            "sender": address(sender_address), "replyTo": [], "toRecipients": [address("agent@example.com")],
            "uniqueBody": {"contentType": "text", "content": "applicant_name: Lin"},
            "receivedDateTime": "2026-10-06T10:00:00+00:00", "hasAttachments": False,
            "internetMessageHeaders": [], **changes}


class Graph:
    """Provider boundary fake only; actual SDK offline model, SQLite and files run."""
    def __init__(self, messages):
        self.messages = messages
        self.posts = []
        self.failure = False
        self.attachments = []

    def request(self, method, url, body=None):
        path = urlsplit(url).path
        if path == "/me":
            return {"id": "mailbox-1", "mail": "agent@example.com"}
        if path == "/me/mailFolders/inbox/messages":
            since = parse_qs(urlsplit(url).query)["$filter"][0].split(" ge ")[1]
            return {"value": [m for m in self.messages if datetime.fromisoformat(m["receivedDateTime"]) >= datetime.fromisoformat(since)]}
        if method == "POST":
            self.posts.append((url, body))
            if self.failure:
                raise TimeoutError("Response lost after provider accepted reply")
            return {}
        parts = path.split("/")
        if path.endswith("/attachments"):
            return {"value": self.attachments}
        if "/attachments/" in path:
            return next(a for a in self.attachments if a["id"] == parts[-1])
        return deepcopy(next(m for m in self.messages if m["id"] == unquote(parts[3])))


def adapter(tmp_path, graph, allowed=("lin@example.com", "bo@example.com")):
    return OutlookInbox(VisaService(tmp_path, "offline", hitl=False), graph, "agent@example.com", allowed)


def test_graph_poll_attachments_restart_and_reply_once(tmp_path):
    graph = Graph([mail(hasAttachments=True)])
    data = (Path(__file__).resolve().parents[1] / "datasets/materials/dev_visitor/identity.pdf").read_bytes()
    graph.attachments = [{"id": "a1", "name": "护照.pdf", "size": len(data), "@odata.type": "#microsoft.graph.fileAttachment",
                          "contentBytes": base64.b64encode(data).decode(), "isInline": False}]
    poll = adapter(tmp_path, graph)
    first = poll.poll("2026-10-06T00:00:00Z")
    result = first["messages"][0]["result"]
    case = poll.service.store.get(result["case_id"])
    assert len(case.documents) == 1 and case.documents[0].content_role == "sample"
    assert not case.automatic_completion and result["proof"] == "graph_mailbox_oauth_test_allowlist"
    assert not graph.posts and first["messages"][0]["send_status"] == "prepared"
    adapter(tmp_path, graph).poll("2026-10-06T00:00:00Z", send_replies=True)
    adapter(tmp_path, graph).poll("2026-10-06T00:00:00Z", send_replies=True)
    assert len(graph.posts) == 1
    assert graph.posts[0][1]["message"]["body"]["content"] == result["reply"]
    assert len(poll.service.store.traces(case.id)) == 1


@pytest.mark.parametrize("change", [
    {"replyTo": [{"emailAddress": {"address": "third-party@example.com"}}]},
    {"sender": {"emailAddress": {"address": "different@example.com"}}},
    {"toRecipients": [{"emailAddress": {"address": "other@example.com"}}]},
    {"uniqueBody": {"contentType": "html", "content": "<img src='https://example.com/tracker'>"}},
    {"internetMessageHeaders": [{"name": "Auto-Submitted", "value": "auto-replied"}]},
])
def test_bad_envelopes_rejected_before_model_or_sending(tmp_path, change):
    graph = Graph([mail(**change)])
    poll = adapter(tmp_path, graph)
    result = poll.poll("2026-10-06T00:00:00Z", send_replies=True)
    assert result["messages"][0]["send_status"] == "rejected" and not graph.posts
    with poll.service.store.connect() as db:
        assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 0


def test_uncertain_send_is_deferred_and_new_messages_keep_advancing(tmp_path):
    graph = Graph([mail()])
    poll = adapter(tmp_path, graph)
    graph.failure = True
    result = poll.poll("2026-10-06T00:00:00Z", send_replies=True)
    assert result["messages"][0]["send_status"] == "retry"
    graph.failure = False
    adapter(tmp_path, graph).poll("2026-10-06T00:00:00Z", send_replies=True)
    assert len(graph.posts) == 1
    graph.messages.append(mail(id="m2", sender_address="bo@example.com", thread="t2", receivedDateTime="2026-10-06T10:01:00+00:00"))
    result = adapter(tmp_path, graph).poll("2026-10-06T00:00:00Z", send_replies=True)
    assert len(graph.posts) == 2 and result["messages"][0]["send_status"] == "sent"


def test_same_conversation_different_sender_is_rejected(tmp_path):
    graph = Graph([mail(), mail(id="m2", sender_address="bo@example.com")])
    result = adapter(tmp_path, graph).poll("2026-10-06T00:00:00Z")
    assert result["messages"][1]["send_status"] == "rejected"


def test_pagination_budget_and_persisted_cursor_do_not_starve_later_mail(tmp_path):
    start = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
    graph = Graph([mail(id=f"m{i}", receivedDateTime=(start + timedelta(minutes=i)).isoformat()) for i in range(26)])
    cases = set()
    for _ in range(13):
        response = adapter(tmp_path, graph).poll("2026-10-06T00:00:00Z", max_messages=2, send_replies=True)
        assert len(response["messages"]) == 2
        cases.update(m["result"]["case_id"] for m in response["messages"])
    assert len(cases) == 1 and len(graph.posts) == 26
    case = adapter(tmp_path, graph).service.store.get(next(iter(cases)))
    assert len(case.history) == 20 and case.history_count == 26


def test_untrusted_graph_pagination_cannot_receive_bearer_token():
    graph = GraphClient(lambda: pytest.fail("Token must not be read for an untrusted URL"))
    with pytest.raises(ValueError):
        graph.request("GET", "https://attacker.example/v1.0/me")


@pytest.mark.parametrize("text", ["age: 30", "/reset", "/exit"])
def test_prepared_reply_is_not_sent_after_case_changes_or_closes(tmp_path, text):
    graph = Graph([mail()])
    adapter(tmp_path, graph).poll("2026-10-06T00:00:00Z")
    graph.messages.append(mail(id="m2", uniqueBody={"contentType": "text", "content": text},
                               receivedDateTime="2026-10-06T10:01:00+00:00"))
    adapter(tmp_path, graph).poll("2026-10-06T00:00:00Z")
    result = adapter(tmp_path, graph).poll("2026-10-06T00:00:00Z", send_replies=True)
    assert [r["send_status"] for r in result["messages"]] == ["superseded", "sent"]
    assert len(graph.posts) == 1 and "/m2/reply" in graph.posts[0][0]


@pytest.mark.parametrize("attachment", [
    {"name": "../passport.pdf", "size": 10},
    {"name": "passport.exe", "size": 10},
    {"name": "passport.pdf", "size": 10 * 1024 * 1024 + 1},
])
def test_invalid_attachments_rejected_before_case_creation(tmp_path, attachment):
    graph = Graph([mail(hasAttachments=True)])
    graph.attachments = [{"id": "a1", **attachment}]
    result = adapter(tmp_path, graph).poll("2026-10-06T00:00:00Z", send_replies=True)
    assert result["messages"][0]["send_status"] == "rejected" and not graph.posts
    with adapter(tmp_path, graph).service.store.connect() as db:
        assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 0


def test_signed_in_mailbox_must_match_configuration(tmp_path):
    graph = Graph([mail()])
    wrong = OutlookInbox(VisaService(tmp_path, "offline"), graph, "other@example.com", ["lin@example.com"])
    with pytest.raises(ValueError, match="does not match"):
        wrong.poll("2026-10-06T00:00:00Z", send_replies=True)
    assert not graph.posts


def test_graph_redirects_are_not_followed():
    with pytest.raises(ValueError, match="redirect"):
        NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://other.example/")
