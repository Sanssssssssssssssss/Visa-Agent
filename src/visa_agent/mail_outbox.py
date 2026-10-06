"""One shared delivery guard for the Graph and IMAP/SMTP pilot adapters."""

from .rules import RULE_VERSION


def send_prepared_reply(store, table, receipt_id, result, enabled, allowed, send):
    # Names are application constants, never input from a message or configuration.
    if table not in {"outlook_receipts", "qq_receipts"}:
        raise ValueError("Unknown mail receipt table")
    with store.transaction() as db:
        row = db.execute(f"SELECT send_status FROM {table} WHERE id=?", (receipt_id,)).fetchone()
        status = row[0]
        if not enabled or status != "prepared":
            return {"result": result, "send_status": status}
        if result.get("mail_sender") not in allowed:
            raise ValueError("Prepared recipient is no longer in the test sender allowlist")
        case = store.get(result["case_id"], db)
        active = db.execute("SELECT case_id,state FROM inbox_sessions WHERE id=?", (result["session_id"],)).fetchone()
        if (not active or active[0] != case.id or case.version != result["version"]
                or active[1] != result["session_state"]
                or (case.rule_version and case.rule_version != RULE_VERSION)):
            db.execute(f"UPDATE {table} SET send_status='superseded' WHERE id=?", (receipt_id,))
            return {"result": result, "send_status": "superseded"}
        # Reservation is committed before the network call. A crash after this
        # point leaves 'sending', which requires inspection rather than a retry.
        db.execute(f"UPDATE {table} SET send_status='sending' WHERE id=?", (receipt_id,))
    try:
        send()
    except Exception as exc:
        with store.transaction() as db:
            db.execute(f"UPDATE {table} SET send_status='uncertain',error='Check Sent Items before retrying' WHERE id=?", (receipt_id,))
        if isinstance(exc, ValueError):
            raise RuntimeError("Mail send outcome uncertain; inspect the sent mailbox") from exc
        raise
    with store.transaction() as db:
        db.execute(f"UPDATE {table} SET send_status='sent' WHERE id=?", (receipt_id,))
    return {"result": result, "send_status": "sent"}
