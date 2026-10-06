"""Adversarial routing, lifecycle and long-conversation checks; no real network."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

import pytest

from visa_agent.agent import build_context
from visa_agent.evidence import Evidence
from visa_agent.inbox import Inbox, Incoming, normalize_sender
from visa_agent.service import VisaService
from visa_agent.types import CaseEvent


def incoming(**changes):
    return Incoming(**({"channel": "email", "account": "main", "thread": "thread-a",
                        "sender": "lin@example.com", "message_id": "message-1", "text": "applicant_name: Lin Example"} | changes))


def test_sender_thread_account_and_message_identity_are_all_checked(tmp_path):
    inbox = Inbox(VisaService(tmp_path, "offline"))
    first = inbox.receive_simulated(incoming())
    for bad in [incoming(sender="other@example.com", message_id="different"),
                incoming(thread="thread-b"), incoming(text="applicant_name: Intruder")]:
        with pytest.raises(ValueError):
            inbox.receive_simulated(bad)
    second = inbox.receive_simulated(incoming(account="second-mailbox", sender="other@example.com"))
    third = inbox.receive_simulated(incoming(channel="whatsapp", sender="+8613812345678"))
    assert len({r["case_id"] for r in (first, second, third)}) == 3
    assert Evidence(inbox.store.get(first["case_id"])).get("applicant_name") == "Lin Example"


@pytest.mark.parametrize("channel,sender", [("email", "not-email"), ("email", "a@example.com\r\nBcc:b@example.com"),
                                            ("email", "a@example.com,b@example.com"), ("whatsapp", "13812345678"),
                                            ("whatsapp", "+001234567890"), ("web", "chosen-id")])
def test_malformed_identity_rejected(channel, sender):
    with pytest.raises(ValueError):
        normalize_sender(channel, sender)


def test_email_aliases_and_local_part_case_are_not_merged():
    assert normalize_sender("email", "Lin@EXAMPLE.COM") == "Lin@example.com"
    assert normalize_sender("email", "lin+visa@example.com") != normalize_sender("email", "lin@example.com")


def test_exit_reset_and_redelivery_are_persistent_and_do_not_call_model(tmp_path):
    inbox = Inbox(VisaService(tmp_path, "offline"))
    start = inbox.receive_simulated(incoming())
    exit_result = inbox.receive_simulated(incoming(message_id="exit", text="/exit"))
    assert exit_result["session_state"] == "closed"
    before = inbox.store.get(start["case_id"]).model_dump()
    closed = inbox.receive_simulated(incoming(message_id="late", text="age: 99"))
    assert closed["session_state"] == "closed"
    assert inbox.store.get(start["case_id"]).model_dump() == before
    inbox = Inbox(VisaService(tmp_path, "offline"))
    reset = incoming(message_id="reset", text="/reset")
    fresh = inbox.receive_simulated(reset)
    assert fresh["case_id"] != start["case_id"]
    assert inbox.receive_simulated(reset)["duplicate"]
    case = inbox.store.get(fresh["case_id"])
    assert not case.facts and not case.documents and not case.history and not case.test_mode
    # Replaying a pre-reset message cannot resurrect its case or pollute the fresh one.
    old = inbox.receive_simulated(incoming())
    assert old["duplicate"] and old["case_id"] == start["case_id"]
    assert inbox.session(start["session_id"])["case_id"] == fresh["case_id"]
    with pytest.raises(ValueError, match="closed"):
        inbox.service.handle_event(CaseEvent(case_id=start["case_id"], event_id="bypass", text="age: 88"))


def test_internal_signature_validates_raw_bytes_freshness_and_schema(tmp_path):
    secret = b"test-only-connector-key-32-bytes-long"
    inbox = Inbox(VisaService(tmp_path, "offline"), connector_secret=secret)
    raw = incoming().model_dump_json().encode()
    signature = hmac.new(secret, b"1000." + raw, hashlib.sha256).hexdigest()
    with pytest.raises(ValueError, match="signature"):
        inbox.receive_signed(raw + b" ", "1000", signature, now=1001)
    with pytest.raises(ValueError, match="expired"):
        inbox.receive_signed(raw, "1000", signature, now=1400)
    good = inbox.receive_signed(raw, "1000", signature, now=1001)
    assert good["proof"] == "internal_connector_hmac"
    assert inbox.receive_signed(raw, "1000", signature, now=1001)["duplicate"]
    malicious = json.dumps(incoming(message_id="injected").model_dump(mode="json") | {"case_id": good["case_id"]}).encode()
    forged_schema_sig = hmac.new(secret, b"1000." + malicious, hashlib.sha256).hexdigest()
    with pytest.raises(ValueError):
        inbox.receive_signed(malicious, "1000", forged_schema_sig, now=1001)


def test_crash_after_business_commit_before_delivery_receipt_is_retry_safe(tmp_path):
    inbox = Inbox(VisaService(tmp_path, "offline"))
    first = inbox.receive_simulated(incoming())
    with inbox.store.transaction() as db:
        db.execute("UPDATE inbox_deliveries SET result=NULL")
    again = Inbox(VisaService(tmp_path, "offline")).receive_simulated(incoming())
    assert again["duplicate"] and again["version"] == first["version"]
    assert len(inbox.store.get(first["case_id"]).facts) == 1


@pytest.mark.parametrize("iteration", range(3))
@pytest.mark.parametrize("hitl", [True, False])
def test_thirty_logical_days_four_interleaved_senders_restart_and_compress(tmp_path, iteration, hitl):
    actors = [("email", "mail", "lin@example.com", "Lin"), ("email", "mail", "alex@example.com", "Alex"),
              ("whatsapp", "wa-1", "+8613812345001", "Wen"), ("whatsapp", "wa-2", "+8613812345001", "Bo")]
    start = datetime(2026, 9, 7, tzinfo=timezone.utc)
    roots = {}
    def deliver(day, actor):
        channel, account, sender, name = actor
        event = incoming(channel=channel, account=account, sender=sender, thread="thread-"+name,
                         message_id=f"{name}-{day}", text="applicant_name: " + name,
                         at=start + timedelta(days=day))
        inbox = Inbox(VisaService(tmp_path, "offline", hitl=hitl))  # Recreate objects for each delivery.
        result = inbox.receive_simulated(event)
        duplicate = Inbox(VisaService(tmp_path, "offline")).receive_simulated(event)
        assert duplicate["duplicate"] and duplicate["case_id"] == result["case_id"]
        return name, result["case_id"]
    for day in range(30):
        with ThreadPoolExecutor(max_workers=4) as pool:
            roots.update(pool.map(lambda a: deliver(day, a), actors))
    assert len(set(roots.values())) == 4
    service = VisaService(tmp_path, "offline")
    for name, case_id in roots.items():
        case = service.store.get(case_id)
        assert case.hitl_enabled == hitl
        assert {f.value for f in case.facts} == {name}
        assert len(case.history) == 20 and case.history_count == 30
        assert len(service.store.dialogue(case.id)) == 30
        prompt, available = build_context(case, CaseEvent(case_id=case.id, event_id="probe", text="下一步？"), [])
        context = json.loads(prompt)
        assert len(context["facts"]) == 1 and context["facts"][0]["source_count"] == 30
        assert len(context["recent_dialogue"]) == 20 and available >= 0


def test_compression_keeps_conflicting_values(tmp_path):
    inbox = Inbox(VisaService(tmp_path, "offline"))
    first = inbox.receive_simulated(incoming())
    for i in range(10):
        inbox.receive_simulated(incoming(message_id=f"m{i}", text="applicant_name: Different Name"))
    case = inbox.store.get(first["case_id"])
    prompt, _ = build_context(case, CaseEvent(case_id=case.id, event_id="probe"), [])
    assert {f["value"] for f in json.loads(prompt)["facts"]} == {"Lin Example", "Different Name"}
    assert any(c.id == "conflict:applicant_name" for c in case.checks)
