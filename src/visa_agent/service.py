"""Application boundary: inbox -> candidate facts -> checks -> explicit review.

No model call can commit an approval. Failed work leaves the raw inbox event
available to replay and conservatively invalidates any earlier approval.
"""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import uuid

from .agent import HISTORY_TURNS, LiveBudget, extract
from .config import load_environment, resolve_hitl
from .guidance import guide
from .delivery import build_pack, manifest, verify_pack
from .conversation import language_for, material_progress, progress_text
from .diagnostics import turn_diagnostics
from .documents import read_document, stage_file
from .evidence import apply_proposal
from .intake import apply_form, write_form
from .rules import RULE_VERSION, evaluate, reply_for, status_for
from .store import Store, digest
from .types import Approval, AutomaticCompletion, CaseEvent, Check, Route, Status, TurnResult, now_utc


class VisaService:
    def __init__(self, root="data", mode="live", *, model_override=None, guidance_model_override=None, budget=None, hitl=None, application_forms=False):
        load_environment()
        if mode not in {"live", "offline"}:
            raise ValueError("mode must be live or offline")
        self.store = Store(root)
        self.mode = mode
        self.hitl_enabled = resolve_hitl(hitl)
        self.application_forms = application_forms
        self.model_override = model_override
        self.guidance_model_override = guidance_model_override
        self.budget = budget or LiveBudget(self.store.root / "live-budget.sqlite3")

    def create_case(self, case_id, *, test_mode=False):
        return self.store.create(case_id, test_mode=test_mode, hitl_enabled=self.hitl_enabled,
                                 application_forms=self.application_forms)

    @staticmethod
    def checked_status(case):
        status = status_for(case.checks)
        return Status.BLOCKED if status == Status.NEEDS_HUMAN and not case.hitl_enabled else status

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
            if case.conversation_closed:
                raise ValueError("Conversation is closed; start a new case before sending input")
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
                        case.automatic_completion = None
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
                if case.conversation_closed:
                    raise ValueError("Conversation closed before processing started")
                trace["before"] = case.model_dump()
                if self.application_forms and not case.application_forms:
                    case.application_forms = True
                    case.version += 1
                    case.approval, case.automatic_completion, case.pack_path = None, None, None
                    case.checks = evaluate(case)
                    case.status = self.checked_status(case)
                case.language = language_for(event.text, case.language)
                if case.rule_version and case.rule_version != RULE_VERSION:
                    case.version += 1
                    case.approval, case.pack_path = None, None
                    case.automatic_completion = None
                    case.status = Status.NEEDS_HUMAN if case.hitl_enabled else Status.BLOCKED
                    case.pending_error = "Rules changed; adviser refresh required"
                if event.kind == "tick":
                    reply = self._tick(case, event)
                else:
                    new_docs = []
                    intent = "continue"
                    guidance = None
                    for original, sha, path in staged:
                        if any(d.sha256 == sha for d in case.documents):
                            continue
                        doc = read_document(path, sha, Path(original).name)
                        case.documents.append(doc)
                        new_docs.append(doc)
                    trace["documents_read"] = [d.model_dump() for d in new_docs]
                    if event.text.strip() or new_docs or event.input_issues:
                        proposal = extract(case, event, [d for d in new_docs if d.kind != "intake"], trace, self.mode, self.budget,
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
                        # Resolve only requested historical citations, scoped to this case.
                        sources = {}
                        for candidate in proposal.facts:
                            if candidate.source_id.startswith("message:"):
                                row = db.execute("SELECT body FROM events WHERE case_id=? AND event_id=?",
                                    (case.id, candidate.source_id.removeprefix("message:"))).fetchone()
                                if row:
                                    sources[candidate.source_id] = json.loads(row[0])["text"]
                        sources[f"message:{event.event_id}"] = event.text
                        trace["unconfirmed_candidates"] = []
                        rejected = apply_proposal(case, proposal, sources,
                                                  unconfirmed=trace["unconfirmed_candidates"],
                                                  current_source=f"message:{event.event_id}")
                        trace["rejected_candidates"] = rejected
                        if rejected:
                            case.extraction_issues[event.event_id] = rejected
                        form_docs = [d for d in new_docs if d.kind == "intake"]
                        if form_docs:
                            from .evidence import Evidence
                            route = Evidence(case).get("route")
                            case.route = Route(route) if route in set(Route) else None
                            case.application_forms = True
                            for doc in form_docs:
                                apply_form(case, doc, trace)
                        case.approval = None
                        case.automatic_completion = None
                        case.rule_version = RULE_VERSION
                        case.checks = evaluate(case)
                        for index, issue in enumerate(event.input_issues):
                            case.checks.append(Check(id=f"input:{index}", status="fail", source="project:mail-parser",
                                                     message=issue))
                        others = db.execute("SELECT event_id FROM events WHERE case_id=? AND event_id<>? "
                                            "AND status IN ('pending','failed')", (case.id, event.event_id)).fetchall()
                        if others:
                            case.checks.append(Check(id="pending_events", status="unknown", human=True,
                                                     source="project:inbox", message="有未完成输入，须重试或由顾问处置。"))
                        case.status = self.checked_status(case)
                        case.pending_error = None
                        if case.status == Status.READY and not case.hitl_enabled:
                            # Collection ends when the versioned checklist is satisfied.
                            # A second model decision cannot add evidence or approve a visa.
                            trace["completion_policy"] = "checked_collection_v1"
                            case.automatic_completion = AutomaticCompletion(version=case.version,
                                manifest_hash=digest(manifest(case)), decision_run_id=run_id,
                                basis="checklist")
                            case.status = Status.COMPLETE
                        if case.status in {Status.READY, Status.COMPLETE}:
                            case.pack_path = build_pack(case, self.store.root)
                        case.form_path = None
                        if (case.application_forms and case.route and case.status not in {Status.COMPLETE, Status.READY}
                                and any(c.id.startswith(("info:", "form:")) and c.status in {"unknown", "fail"} for c in case.checks)):
                            case.form_path = write_form(case, self.store.root / "forms" / case.id / f"v{case.version}" / "application-information.xlsx")
                        try:
                            guidance = guide(case, event, trace, "offline" if self.model_override else self.mode,
                                             self.budget, model_override=self.guidance_model_override)
                        except Exception as exc:
                            # A wording failure must not roll back successfully read
                            # evidence. Still send a truthful service notice.
                            trace["reply_error"] = type(exc).__name__
                            from .types import Guidance
                            guidance = Guidance(reply=(
                                "抱歉，我已保存这次的信息，但暂时没能整理好详细回复。下方是当前进度；您可以继续回复这封邮件。"
                                if case.language == "zh" else
                                "Sorry, your update is saved, but I couldn't prepare the detailed reply just now. Your current progress is below; you can continue in this email thread."))
                    reply = reply_for(case, text=event.text, intent=intent, received_count=len(staged),
                                      received_names=[Path(original).name for original, _, _ in staged], guidance=guidance)
                    case.last_contact = max(case.last_contact, event.at.isoformat())
                    case.reminder_count = 0
                    case.last_reminder = None
                    case.history_count = max(case.history_count, len(case.history)) + 1
                    case.history.append({"event_id": event.event_id, "text": event.text,
                                         "reply": reply, "at": event.at.isoformat()})
                    case.history = case.history[-HISTORY_TURNS:]
                result = TurnResult(case_id=case.id, version=case.version, status=case.status,
                                    reply=reply, run_id=run_id, pack_path=case.pack_path, form_path=case.form_path)
                self.store.save(case, db)
                db.execute("UPDATE events SET status='done',result=?,error=NULL WHERE case_id=? AND event_id=?",
                           (result.model_dump_json(), case.id, event.event_id))
                trace["after"] = case.model_dump()
                trace["diagnostics"] = turn_diagnostics(case, trace)
                trace["customer_reply"] = reply
                trace["material_progress"] = material_progress(case)
                self.store.record_run(case.id, run_id, trace, db)
                return result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            for name in ("VISA_API_KEY", "DEEPSEEK_API_KEY"):
                if os.getenv(name):
                    error = error.replace(os.environ[name], "[REDACTED]")
            fallback = None
            with self.store.transaction() as db:
                case = self.store.get(event.case_id, db)
                case.language = language_for(event.text, case.language)
                case.status = Status.NEEDS_HUMAN if case.hitl_enabled else Status.BLOCKED
                case.approval, case.automatic_completion, case.pack_path = None, None, None
                case.pending_error = error
                self.store.save(case, db)
                db.execute("UPDATE events SET status='failed',error=? WHERE case_id=? AND event_id=?",
                           (error, case.id, event.event_id))
                trace["error"] = error
                trace["after"] = case.model_dump()
                trace["diagnostics"] = turn_diagnostics(case, trace)
            if self.mode == "live" and not self.model_override and trace.get("http_requests", 0) < 4:
                try:
                    fallback = guide(case, event, trace, self.mode, self.budget)
                except Exception as reply_exc:
                    trace["reply_error"] = type(reply_exc).__name__
            reply = reply_for(case, guidance=fallback) if fallback and fallback.reply.strip() else (
                "抱歉，这次没能完成检查，原始输入已经保存。您暂时不用重复上传，可以继续回复这封邮件；这次检查仍未完成。"
                if case.language == "zh" else
                "Sorry, this check could not be completed. Your original input is saved; you don't need to upload it again yet. You can continue replying here. This check is still incomplete.") + "\n\n" + progress_text(case)
            trace["customer_reply"] = reply
            with self.store.transaction() as db:
                self.store.record_run(case.id, run_id, trace, db)
            return TurnResult(case_id=case.id, version=case.version, status=case.status, run_id=run_id,
                              reply=reply, error=error)

    @staticmethod
    def _tick(case, event):
        if case.status != Status.WAIT_USER:
            return ("当前状态不需要自动提醒。" if case.language == "zh" else "No reminder is needed in the current state.") + "\n" + progress_text(case)
        if case.reminder_count >= 2:
            if case.hitl_enabled:
                return ("已达到两次提醒上限，保留等待状态，请顾问跟进。" if case.language == "zh" else "Two reminders have been sent. We will keep your case open for adviser follow-up.") + "\n" + progress_text(case)
            return ("已达到两次提醒上限，案件保留等待状态；您可以随时回复继续。" if case.language == "zh" else "Two reminders have been sent. Your case stays open; reply whenever you are ready to continue.") + "\n" + progress_text(case)
        reference = datetime.fromisoformat(case.last_reminder or case.last_contact)
        if event.at < reference + timedelta(hours=24):
            return ("尚未到提醒时间。" if case.language == "zh" else "The next reminder is not due yet.") + "\n" + progress_text(case)
        case.reminder_count += 1
        case.last_reminder = event.at.isoformat()
        return ("材料准备提醒：\n" if case.language == "zh" else "Document preparation reminder:\n") + reply_for(case)

    def review_case(self, case_id, expected_version, decision, notes, *, reviewer="local-adviser", target=None):
        if not notes.strip() or not reviewer.strip():
            raise ValueError("Reviewer and review notes are required")
        allowed = {"approve", "request_changes", "confirm_fact", "reject_document", "accept_document", "dismiss_event", "dismiss_extraction", "refresh"}
        if decision not in allowed:
            raise ValueError(f"Unsupported review decision: {decision}")
        with self.store.transaction() as db:
            case = self.store.get(case_id, db)
            if not case.hitl_enabled:
                raise ValueError("HITL is disabled for this case; no review endpoint is enabled")
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
                if decision == "dismiss_extraction":
                    if target not in case.extraction_issues:
                        raise ValueError("Extraction issue event not found")
                    del case.extraction_issues[target]
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
