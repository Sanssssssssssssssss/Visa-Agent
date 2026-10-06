# Agent design and delivery reliability

[简体中文](architecture.zh-CN.md) · [Source walkthrough](implementation.md) · [Test map](../TESTING.md)

The unit of work is one incoming event. The system persists it, advances a case, saves the response, and stops. A later email continues the same case. There is no open-ended background agent loop while a customer gathers documents.

## Responsibilities and choices

| Layer | Implementation | Reason |
|---|---|---|
| Model runtime | PydanticAI structured `Proposal` / `Guidance` | Typed output, tool loop and offline test models |
| Document reading | pypdf, PDFium, RapidOCR; original/rendered images | Inspectable page text plus visual input |
| Business workflow | Direct functions in `service.py`, `rules.py`, `evidence.py` | Small enough to read; explicit checks and stop states |
| Persistence | SQLite transactions, unique keys, SHA-256 files | Restart and deduplication without a workflow cluster |
| Email | Standard-library IMAP/MIME/SMTP; local connector/outbox | Mature protocol libraries, project-specific case routing |
| Next channel | Chatwoot boundary, currently a design | Reuse channel workspace instead of forking a Rails/Vue application |

Camunda's KYC sample inspired waiting for missing documents; DocProof inspired separating extraction from validation; LangChain email examples informed evaluation and handoff. These are design references, not installed runtime engines. The project does not claim to have reused a complete visa workflow framework. [Provenance](../THIRD_PARTY_NOTICES.md).

## Follow one message

1. `QQInbox.poll()` reads INBOX without marking/deleting mail. Account + UIDVALIDITY + UID track the scan; Message-ID and MIME fingerprint identify delivery.
2. `QQInbox.receive()` resolves email references. `Inbox._receive()` binds channel/account/thread/sender to a case; a customer cannot supply someone else's case ID.
3. `VisaService.handle_event()` persists the event, invalidates stale approval, then reads attachments and extracts proposed facts. A source is a message or a particular document page.
4. `apply_proposal()` validates source membership, quotes and supported value formats. Conflicts retain both values; assertions in email cannot substitute for file evidence.
5. `rules.evaluate()` computes applicable requirements and blockers. After checks, `guidance.guide()` chooses up to three next questions from actual unresolved check IDs.
6. The application saves state, facts, checks, reply and trace. On completion, `build_pack()` and `verify_pack()` check the export; `send_prepared_reply()` checks current version/rules before sending.

SQLite currently holds a write transaction across model work, serializing cases. This gives simple recovery semantics at low throughput. A larger deployment should first add durable tasks and per-case leases; adding more autonomous agents does not solve the bottleneck.

## Uncertainty is recorded

| Uncertainty | Behavior |
|---|---|
| Route or applicability unknown | Ask for the missing condition; do not treat it as “not applicable” |
| Unsupported legal/business branch | `NEEDS_HUMAN`; no speculative automatic pass |
| OCR failure, missing page or truncated reading | Explicit reading problem; document cannot silently satisfy evidence |
| Model value lacks a valid source | Reject or retain as unconfirmed; no silent fact write |
| Contradictory facts | Preserve both sources and a blocker |
| Document authenticity | Outside automated validation; do not claim forensic verification |
| Send timeout after SMTP may have accepted | `uncertain`; operator checks before retrying |

The initial false-completion bug for self-written field PDFs was reproduced and fixed; its receipt and remaining model-classification limits are in [document-quality.md](document-quality.md). Citation validation proves where text came from, not that the model interpreted every sentence correctly.

## State and controls

| State | Meaning |
|---|---|
| `WAIT_USER` | A question, document or clearer upload is needed |
| `NEEDS_HUMAN` | Unsupported branch, conflict or judgment requiring review |
| `BLOCKED` | A processing/model/validation failure needs diagnosis |
| `READY_FOR_REVIEW` | Current checklist passed and HITL is enabled |
| `COMPLETE` | Current collection checklist completed under the configured review policy |

HITL and sample mode are independent, operator-controlled case settings. With HITL on, an independent review approves the current case version and evidence manifest. With it off, the application records automatic checklist completion, not a fictional human approval. New evidence or rule changes invalidate the old decision. Sample mode admits labelled synthetic evidence for demonstrations; it does not bypass missing facts, conflicts or unreadable files.

## Context and bounded work

Each turn includes the service persona, route SOP, current structured facts/checks, new input/evidence excerpts and up to 20 recent full turns. The working budget is 32,000 characters: shorten excerpts first, then drop older dialogue; stop if essential state still will not fit. Complete messages/files stay in local storage. The character limit is not a provider token guarantee.

The model can read only evidence already belonging to its case. Repeated no-progress reads stop; model extraction, tools, retries and guidance share four HTTP requests per event. One transient retry is allowed; the SDK's hidden retries are disabled. Cumulative usage is recorded and uncapped by default. There is no model-call cost while waiting for customer input.

The [SOUL](../src/visa_agent/prompts/SOUL.md) defines a warm, plain-language assistant. The model chooses priorities; application rendering supplies accurate status/progress, bilingual wording and the submission handover. Document text cannot replace these instructions or grant new tools.

## Debugging contract

Read `trace` in this order: original quote → proposed field → accepted/unconfirmed fact → rule result → state → rendered reply → mail receipt. Logs include model/prompt/rule versions, usage and run IDs. Never publish raw customer traces. [Deployment troubleshooting](deployment.md#troubleshoot-and-upgrade).
