"""One shared delivery guard for the Graph and IMAP/SMTP pilot adapters."""

import time

from .rules import RULE_VERSION


def prepare_outbox(db):
    db.execute("CREATE TABLE IF NOT EXISTS mail_attempts (receipt_table TEXT, receipt_id TEXT, "
               "attempts INTEGER, next_attempt REAL, error_type TEXT, PRIMARY KEY(receipt_table,receipt_id))")


def pending_replies(store, table, account, limit):
    if table not in {"outlook_receipts", "qq_receipts"}:
        raise ValueError("Unknown mail receipt table")
    with store.transaction() as db:
        prepare_outbox(db)
        return db.execute(f"SELECT r.* FROM {table} r LEFT JOIN mail_attempts a "
                          "ON a.receipt_table=? AND a.receipt_id=r.id WHERE r.account=? "
                          "AND r.send_status IN ('prepared','retry','uncertain','sending') "
                          "AND COALESCE(a.next_attempt,0)<=? ORDER BY r.rowid LIMIT ?",
                          (table, account, time.time(), limit)).fetchall()


def send_prepared_reply(store, table, receipt_id, result, enabled, allowed, send):
    # Names are application constants, never input from a message or configuration.
    if table not in {"outlook_receipts", "qq_receipts"}:
        raise ValueError("Unknown mail receipt table")
    with store.transaction() as db:
        prepare_outbox(db)
        row = db.execute(f"SELECT send_status FROM {table} WHERE id=?", (receipt_id,)).fetchone()
        status = row[0]
        if not enabled or status not in {"prepared", "retry", "uncertain", "sending"}:
            return {"result": result, "send_status": status}
        attempt = db.execute("SELECT attempts,next_attempt FROM mail_attempts WHERE receipt_table=? AND receipt_id=?",
                             (table, receipt_id)).fetchone()
        if attempt and attempt[1] > time.time():
            return {"result": result, "send_status": status, "retry_after_seconds": round(attempt[1] - time.time())}
        if result.get("mail_sender") not in allowed:
            raise ValueError("Prepared recipient is no longer in the test sender allowlist")
        case = store.get(result["case_id"], db)
        active = db.execute("SELECT case_id,state FROM inbox_sessions WHERE id=?", (result["session_id"],)).fetchone()
        if (not active or active[0] != case.id or case.version != result["version"]
                or active[1] != result["session_state"]
                or (case.rule_version and case.rule_version != RULE_VERSION and not result.get("error"))):
            db.execute(f"UPDATE {table} SET send_status='superseded' WHERE id=?", (receipt_id,))
            return {"result": result, "send_status": "superseded"}
        # At-least-once delivery: retry a crash/ambiguous SMTP response using the
        # same Message-ID. Providers may still deliver a duplicate. A reservation
        # prevents concurrent workers sending while the first attempt is active.
        db.execute(f"UPDATE {table} SET send_status='sending' WHERE id=?", (receipt_id,))
        attempts = (attempt[0] if attempt else 0) + 1
        db.execute("INSERT OR REPLACE INTO mail_attempts VALUES (?,?,?,?,NULL)",
                   (table, receipt_id, attempts, time.time() + 120))
    try:
        send()
    except Exception as exc:
        delay = min(300, 15 * 2 ** min(attempts - 1, 5))
        with store.transaction() as db:
            db.execute(f"UPDATE {table} SET send_status='retry',error='Delivery unconfirmed; retry scheduled' WHERE id=?", (receipt_id,))
            db.execute("UPDATE mail_attempts SET next_attempt=?,error_type=? WHERE receipt_table=? AND receipt_id=?",
                       (time.time() + delay, type(exc).__name__, table, receipt_id))
        return {"result": result, "send_status": "retry", "error_type": type(exc).__name__, "retry_after_seconds": delay}
    with store.transaction() as db:
        db.execute(f"UPDATE {table} SET send_status='sent',error=NULL WHERE id=?", (receipt_id,))
    return {"result": result, "send_status": "sent"}
