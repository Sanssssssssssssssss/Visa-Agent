# Follow an email through the code

[简体中文](implementation.md) · [Architecture](architecture.md) · [Configuration](configuration.md) · [Troubleshooting](troubleshooting.md)

The business entrypoint is `VisaService.handle_event(CaseEvent) -> TurnResult`. It handles one external event and returns. The next customer message advances the persisted case; waiting does not run the model.

## Entry points and stored records

| Step | Code | Input → saved result |
|---|---|---|
| Retrieve | [QQConnection / QQInbox.poll](../src/visa_agent/qq_mail.py) | Read-only INBOX → UID cursor, MIME input |
| Identify | [QQInbox.receive](../src/visa_agent/qq_mail.py), [Inbox](../src/visa_agent/inbox.py) | Account/thread/sender/message ID → bound case, receipt |
| Read | [stage_file / read_document](../src/visa_agent/documents.py), [visual_inputs](../src/visa_agent/vision.py) | Attachment bytes → hash, pages, OCR, reading problems and model images |
| Extract | [extract / make_agent](../src/visa_agent/agent.py) | Case context and sources → typed `Proposal`, tool and usage trace |
| Apply | [apply_proposal](../src/visa_agent/evidence.py) | Candidate values/quotes → accepted, unconfirmed or conflicting facts |
| Check | [evaluate](../src/visa_agent/rules.py), [intake](../src/visa_agent/intake.py) | Facts/evidence/route → requirement and application-information results |
| Deliver | [build_pack / verify_pack](../src/visa_agent/delivery.py) | Passed checklist/review policy → ZIP, manifest and provenance |
| Reply | [guide](../src/visa_agent/guidance.py), [conversation](../src/visa_agent/conversation.py) | Actual state, missing items, available files → model-written reply and progress |
| Send | [send_prepared_reply](../src/visa_agent/mail_outbox.py) | Current-version reply → SMTP acceptance or persisted retry |

Start with [service.py](../src/visa_agent/service.py); open helper modules when their calls occur. [Store](../src/visa_agent/store.py) contains the transaction and persistence methods. The local web simulator is optional; Docker's email worker exposes no product port.

## Identity, duplicates and transactions

Customers cannot select a case ID. The inbox binds `channel/account/thread/sender`; RFC References and In-Reply-To continue a thread. Unknown human senders can start cases when intake is open. A different sender's references cannot transfer an existing case. Message-ID plus input hash deduplicates redelivery; the same ID with changed content is rejected.

`handle_event()` first saves the inbox event, increments the version for new business input and invalidates old approval. A second write transaction reads documents, runs the model, applies facts, checks the case and saves the response/trace together. A failure rolls that transaction back and records the failed event separately. External file writes can leave unreferenced files; those do not become approved evidence.

SQLite uses `BEGIN IMMEDIATE` and currently holds the writer through model work. Cases process serially, including across customers. This MVP favors inspectable recovery at low throughput; scaling requires shorter transactions and durable per-case jobs, not additional free-running agents.

## Reading does not mean acceptance

PDF text extraction uses pypdf. Scanned, masked or graphically filled pages render with PDFium and pass through RapidOCR. Original images/rendered pages also reach the configured vision-capable model; trace records page/image hashes without base64.

`Proposal` contains document classifications and candidate facts with source ID, page, exact quote and confidence. `apply_proposal()` checks case membership, page existence, quote location and supported value formats. Money comparisons use `Decimal`, dates use date parsing. Self-reported email facts remain distinct from document evidence; a quote match does not establish correct semantic interpretation.

Material roles distinguish evidence, sample, self-report, unrelated and uncertain. Only explicitly configured demo cases admit marked samples. Unreadable or rejected documents, low-confidence fields and conflicting values cannot silently satisfy a requirement. The model cannot enable sample mode, change review policy or authenticate a document.

Bank extraction has one SDK recheck opportunity when a relevant readable page omitted a required field. It rereads saved evidence within the shared request budget, using already-known fields; `bank_extraction_recheck` records what remained missing. Unresolved fields stay unknown. Finance waits for CAS/budget/application-date prerequisites separately from receipt and document readability; [the original failure](finance-receipt.md) explains why.

## Model work and context

[SOUL.md](../src/visa_agent/prompts/SOUL.md) describes a warm adviser. Extraction instructions define field/source contracts; guidance instructions provide the actual current state. `Guidance.reply` supplies normal customer wording, including the final handover. The application appends measured emoji progress, separating received evidence from checked categories and application information.

The context is rebuilt from structured case facts, versioned SOP/checks, new sources and up to 20 recent full turns. It shortens document excerpts first, then removes old whole turns to fit 32,000 characters; essential state that cannot fit stops processing. Original events and files persist. This avoids a model summary silently changing amounts or dates; it is not a token-level provider limit.

`read_evidence(document_id, page)` only reads saved pages belonging to the current case. Repeated no-progress reads stop. Four HTTP requests per event are shared by extraction, tools, schema retries, a transient retry and guidance. The SDK's own hidden retries are disabled. [LiveBudget](../src/visa_agent/agent.py) persists request accounting across restart; cumulative limits are optional.

If reply generation fails after extraction, accepted facts stay saved and a service notice is prepared. If extraction/tool execution fails, the failed input remains recorded; the remaining budget may generate an explanation, then a non-empty fallback is used. Errors are not converted into completed cases. [Diagnostics](../src/visa_agent/diagnostics.py) record stage, category, source and recovery action.

## States, review and exports

`WAIT_USER` asks for information/files; `NEEDS_HUMAN` records unsupported branches or review needs; `BLOCKED` records processing failure. Applicable checks must pass, with no unresolved blockers, before `READY_FOR_REVIEW` with HITL on or automatic `COMPLETE` with HITL off. Unknown and unimplemented checks cannot pass. Turning HITL off only removes final approval, not evidence requirements.

`review_case(case_id, expected_version, decision, notes)` is independent of model tools. Approval binds the current case/rule version and evidence manifest. New inputs or relevant code/rule changes invalidate old decisions. The automatic path records `automatic_completion` rather than inventing human approval.

The ZIP preserves original bytes, a bilingual completed worksheet, `START-HERE.html`, submission guidance, checks and provenance. `verify_pack()` checks contents and hashes. Completed mail attaches it as `visa-materials.zip` if under 18 MB. The ZIP is for organization and delivery; the customer still completes the official application and uploads individual files as instructed.

## Mail recovery and deployment

`qq_cursor` retains scan position, `qq_threads` retains references and `qq_receipts` retains prepared/sent results. The shared outbox checks current case/rule versions before sending. `mail_attempts` persists retry times; ambiguous SMTP responses retry with the same Message-ID, so duplicate delivery remains possible. `sent` means provider acceptance, not customer receipt.

`/reset` and `/start` create a fresh case without deleting the old audit; `/exit` closes the conversation; `/status` reads progress. These commands do not call the model. Sender isolation survives restart.

[container_entrypoint.py](../scripts/container_entrypoint.py) initializes intake once. [mail_worker_lock](../src/visa_agent/worker.py) prevents concurrent workers for one data directory. The worker reloads intake/sample policy each poll. Graceful stop finishes the current message and preserves unprocessed cursor entries. Container health checks inspect local status without model/network calls. [Backup/restore](docker.md#backup-and-restore) requires a stopped writer and the same absolute data path.

To debug, follow **source page → candidate field → accepted/unconfirmed fact → rule → state → customer reply → mail receipt**. `inspect`, `trace` and `events` expose the stored results; hidden model reasoning is not recorded. Keep customer traces private. [Test coverage](../TESTING.md) links each contract to the regression that exercises it.
