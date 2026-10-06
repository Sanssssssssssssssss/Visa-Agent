"""Application boundary: inbox -> candidate facts -> checks -> explicit review.

No model call can commit an approval. Failed work leaves the raw inbox event
available to replay and conservatively invalidates any earlier approval.
"""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import uuid

from .agent import LiveBudget, extract
from .delivery import build_pack, manifest, verify_pack
from .conversation import language_for, material_progress, progress_text
from .diagnostics import turn_diagnostics
from .documents import read_document, stage_file
from .evidence import apply_proposal
from .rules import RULE_VERSION, evaluate, reply_for, status_for
from .store import Store, digest
from .types import Approval, CaseEvent, Check, Status, TurnResult, now_utc


class VisaService:
    def __init__(self, root="data", mode="live", *, model_override=None, budget=None):
        if mode not in {"live", "offline"}:
            raise ValueError("mode must be live or offline")
        self.store = Store(root)
        self.mode = mode
        self.model_override = model_override
        self.budget = budget or LiveBudget(self.store.root / "live-budget.sqlite3")

    def handle_event(self, event: CaseEvent) -> TurnResult:
        staged = [(p, *stage_file(p, self.store.root)) for p in event.attachments]
        body = event.model_dump(mode="json")
        identity = {**body, "attachments": [sha for _, sha, _ in staged]}
        if event.kind != "tick":
            identity.pop("at")  # Redelivery can have a different receipt timestamp.
        input_hash = digest(identity)
        run_id = uuid.uuid4().hex
        trace = {"input": body, "mode": self.mode, "rule_version": RULE_VERSION}
        with self.store.transaction() as db:
            case = self.store.get(event.case_id, db)
            old = db.execute("SELECT * FROM events WHERE case_id=? AND event_id=?",
                             (case.id, event.event_id)).fetchone()
            if old:
                if old["input_hash"] != input_hash:
                    raise ValueError("Event ID reused with different content")
                if old["status"] == "done":
                    result = TurnResult.model_validate_json(old["result"])
                    result.duplicate = True
                    return result
                if old["status"] == "dismissed":
                    raise ValueError("Event was dismissed by an adviser; use a new event ID")
            else:
                db.execute("INSERT INTO events VALUES (?,?,?,?, 'pending', NULL,NULL)",
                           (case.id, event.event_id, input_hash, json.dumps(body, ensure_ascii=False)))
                if event.kind != "tick":
                    pure_duplicate = not event.text.strip() and bool(staged) and all(
                        any(d.sha256 == sha for d in case.documents) for _, sha, _ in staged)
                    if not pure_duplicate:
                        case.version += 1
                        case.approval = None
                        case.pack_path = None
                        case.status = Status.WAIT_USER
                        case.pending_error = "Incoming event has not completed"
                        self.store.save(case, db)
        try:
            with self.store.transaction() as db:
                # Recheck under the write lock: two processes may have received the same event.
                row = db.execute("SELECT status,result FROM events WHERE case_id=? AND event_id=?",
                                 (event.case_id, event.event_id)).fetchone()
                if row["status"] == "done":
                    return TurnResult.model_validate_json(row["result"]).model_copy(update={"duplicate": True})
                case = self.store.get(event.case_id, db)
                trace["before"] = case.model_dump()
                case.language = language_for(event.text, case.language)
                if case.rule_version and case.rule_version != RULE_VERSION:
                    case.version += 1
                    case.approval, case.pack_path = None, None
                    case.status = Status.NEEDS_HUMAN
                    case.pending_error = "Rules changed; adviser refresh required"
                if event.kind == "tick":
                    reply = self._tick(case, event)
                else:
                    new_docs = []
                    intent = "continue"
                    for original, sha, path in staged:
                        if any(d.sha256 == sha for d in case.documents):
                            continue
                        doc = read_document(path, sha, Path(original).name)
                        case.documents.append(doc)
                        new_docs.append(doc)
                    trace["documents_read"] = [d.model_dump() for d in new_docs]
                    if event.text.strip() or new_docs:
                        proposal = extract(case, event, new_docs, trace, self.mode, self.budget,
                                           self.model_override)
                        intent = proposal.intent
                        for item in trace.get("visual_inputs", []):
                            if not item["sent"]:
                                doc = next(d for d in case.documents if d.id == item["document_id"])
                                doc.problems.append(f"Visual input unavailable page {item['page']}: {item['reason']}")
                        for doc in case.documents:
                            if doc.id in trace.get("context_limited_documents", []):
                                problem = "Model context capacity exceeded; full-page review required"
                                if problem not in doc.problems:
                                    doc.problems.append(problem)
                        sources = {f"message:{h['event_id']}": h["text"] for h in case.history}
                        sources[f"message:{event.event_id}"] = event.text
                        rejected = apply_proposal(case, proposal, sources)
                        trace["rejected_candidates"] = rejected
                        case.approval = None
                        case.rule_version = RULE_VERSION
                        case.checks = evaluate(case)
                        if rejected:
                            case.checks.append(Check(id="extraction_review", status="unknown", human=True,
                                                     source="project:source-grounding",
                                                     message="部分字段无法核对来源，请顾问检查提取结果。"))
                        others = db.execute("SELECT event_id FROM events WHERE case_id=? AND event_id<>? "
                                            "AND status IN ('pending','failed')", (case.id, event.event_id)).fetchall()
                        if others:
                            case.checks.append(Check(id="pending_events", status="unknown", human=True,
                                                     source="project:inbox", message="有未完成输入，须重试或由顾问处置。"))
                        case.status = status_for(case.checks)
                        case.pending_error = None
                        if case.status == Status.READY:
                            case.pack_path = build_pack(case, self.store.root)
                    reply = reply_for(case, text=event.text, intent=intent, received_count=len(staged))
                    case.last_contact = max(case.last_contact, event.at.isoformat())
                    case.reminder_count = 0
                    case.last_reminder = None
                    case.history.append({"event_id": event.event_id, "text": event.text,
                                         "reply": reply, "at": event.at.isoformat()})
                result = TurnResult(case_id=case.id, version=case.version, status=case.status,
                                    reply=reply, run_id=run_id, pack_path=case.pack_path)
                self.store.save(case, db)
                db.execute("UPDATE events SET status='done',result=?,error=NULL WHERE case_id=? AND event_id=?",
                           (result.model_dump_json(), case.id, event.event_id))
                trace["after"] = case.model_dump()
                trace["diagnostics"] = turn_diagnostics(case, trace)
                trace["material_progress"] = material_progress(case)
                self.store.record_run(case.id, run_id, trace, db)
                return result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            for name in ("VISA_API_KEY", "DEEPSEEK_API_KEY"):
                if os.getenv(name):
                    error = error.replace(os.environ[name], "[REDACTED]")
            with self.store.transaction() as db:
                case = self.store.get(event.case_id, db)
                case.language = language_for(event.text, case.language)
                case.status, case.approval, case.pack_path = Status.NEEDS_HUMAN, None, None
                case.pending_error = error
                self.store.save(case, db)
                db.execute("UPDATE events SET status='failed',error=? WHERE case_id=? AND event_id=?",
                           (error, case.id, event.event_id))
                trace["error"] = error
                trace["after"] = case.model_dump()
                trace["diagnostics"] = turn_diagnostics(case, trace)
                self.store.record_run(case.id, run_id, trace, db)
            return TurnResult(case_id=case.id, version=case.version, status=case.status, run_id=run_id,
                              reply=("抱歉，这次没能完成检查，原始输入已经保存。需要由工作人员处理后重试，您暂时不用重复上传。" if case.language == "zh" else
                                     "Sorry, this check could not be completed. Your original input is saved. Staff need to resolve the issue before retrying; you do not need to upload it again yet.") + "\n\n" + progress_text(case), error=error)

    @staticmethod
    def _tick(case, event):
        if case.status != Status.WAIT_USER:
            return ("当前状态不需要自动提醒。" if case.language == "zh" else "No reminder is needed in the current state.") + "\n" + progress_text(case)
        if case.reminder_count >= 2:
            return ("已达到两次提醒上限，保留等待状态，请顾问跟进。" if case.language == "zh" else "Two reminders have been sent. We will keep your case open for adviser follow-up.") + "\n" + progress_text(case)
        reference = datetime.fromisoformat(case.last_reminder or case.last_contact)
        if event.at < reference + timedelta(hours=24):
            return ("尚未到提醒时间。" if case.language == "zh" else "The next reminder is not due yet.") + "\n" + progress_text(case)
        case.reminder_count += 1
        case.last_reminder = event.at.isoformat()
        return ("材料准备提醒：\n" if case.language == "zh" else "Document preparation reminder:\n") + reply_for(case)

    def review_case(self, case_id, expected_version, decision, notes, *, reviewer="local-adviser", target=None):
        if not notes.strip() or not reviewer.strip():
            raise ValueError("Reviewer and review notes are required")
        allowed = {"approve", "request_changes", "confirm_fact", "reject_document", "accept_document", "dismiss_event", "refresh"}
        if decision not in allowed:
            raise ValueError(f"Unsupported review decision: {decision}")
        with self.store.transaction() as db:
            case = self.store.get(case_id, db)
            if case.version != expected_version:
                raise ValueError("Stale review: case version changed")
            audit = {"decision": decision, "reviewer": reviewer, "notes": notes,
                     "target": target, "at": now_utc(), "version": case.version}
            if decision == "approve":
                pending = db.execute("SELECT 1 FROM events WHERE case_id=? AND status IN ('pending','failed')",
                                     (case.id,)).fetchone()
                if pending or case.pending_error or case.rule_version != RULE_VERSION:
                    raise ValueError("Unprocessed input or changed rules; refresh/retry before approval")
                if case.status != Status.READY or status_for(evaluate(case)) != Status.READY:
                    raise ValueError("Blocking checks remain; approval cannot bypass them")
                expected_hash = digest(manifest(case))
                if not case.pack_path or not Path(case.pack_path).is_file():
                    raise ValueError("Review pack missing")
                verify_pack(case)
                case.approval = Approval(version=case.version, manifest_hash=expected_hash,
                                         reviewer=reviewer, notes=notes)
                case.status = Status.COMPLETE
                case.reviews.append(audit)
                case.pack_path = build_pack(case, self.store.root)
            else:
                if decision == "confirm_fact":
                    selected = next((f for f in case.facts if f.id == target), None)
                    if selected is None:
                        raise ValueError("Fact not found")
                    for fact in case.facts:
                        if fact.key == selected.key:
                            fact.active = fact.id == target
                    selected.confirmed_by = reviewer
                    selected.active = True
                if decision in {"reject_document", "accept_document"}:
                    doc = next((d for d in case.documents if d.id == target), None)
                    if doc is None:
                        raise ValueError("Document not found")
                    if decision == "reject_document":
                        doc.rejected = True
                    else:
                        if not doc.pages:
                            raise ValueError("An unreadable file needs replacement, not an override")
                        doc.problems = []
                        doc.rejected = False
                if decision == "dismiss_event":
                    result = db.execute("UPDATE events SET status='dismissed' WHERE case_id=? AND event_id=? "
                                        "AND status IN ('pending','failed')", (case.id, target))
                    if not result.rowcount:
                        raise ValueError("Pending/failed event not found")
                case.version += 1
                case.approval, case.pack_path = None, None
                case.rule_version = RULE_VERSION
                case.checks = evaluate(case)
                remaining = db.execute("SELECT 1 FROM events WHERE case_id=? AND status IN ('pending','failed')",
                                       (case.id,)).fetchone()
                case.pending_error = "Unprocessed input remains" if remaining else None
                case.status = Status.NEEDS_HUMAN if remaining else status_for(case.checks)
                if decision == "request_changes":
                    case.status = Status.WAIT_USER
                    case.pending_error = notes
                case.reviews.append(audit)
                if case.status == Status.READY:
                    case.pack_path = build_pack(case, self.store.root)
            self.store.save(case, db)
            self.store.record_run(case.id, uuid.uuid4().hex, {"review": audit, "after": case.model_dump()}, db)
            return case
