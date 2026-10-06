# Troubleshooting

[简体中文](troubleshooting.zh-CN.md) · [Configuration](configuration.md) · [Email walkthrough](channels/email.md)

Start with the layer that failed: inbox retrieval, case processing, then outbound delivery. A sent email is not proof that the case completed; `COMPLETE` is not proof that a visa was submitted.

## No reply arrives

```sh
uv run python scripts/mail_service.py status
```

For Docker:

```sh
docker compose ps
docker compose logs --tail 30 agent
docker compose exec agent python -m visa_agent.qq_mail status --data /data
```

Check `running`, `last_poll.at` and `last_poll.error_type`. OCR/model work delays the poll timestamp. The native host must stay awake and connected. Look in the customer spam folder and the agent's INBOX; this connector does not scan other folders.

| Observation | Next check |
|---|---|
| Worker is stopped | Read `worker.stderr.log`; fix model/mail credentials, then restart using the deployment guide |
| Worker runs but no input is processed | Email arrived after saved `since`; correct agent address; message is in INBOX; open intake has `accept_all=true`, `require_tag=false` |
| Sender is rejected | Inspect `qq-rejections/`; inconsistent From/Reply-To, another sender's references and automatic replies are not new customer input |
| Processing fails | Find the case ID in `qq-watch-last.json` or `worker.stdout.log`, then inspect the trace |
| Reply is `retry` | SMTP has not confirmed delivery; the persistent outbox retries with backoff, preserving Message-ID |
| Reply is `sent` | SMTP accepted it; client receipt/read status is not guaranteed |

Use `python -m visa_agent.qq_mail probe --data <directory>` to check IMAP/SMTP login without sending a customer email. Network failures retain the cursor. Avoid starting a second worker or deleting persistent data to diagnose a timeout.

## “I sent three files; why are only two checked?”

Received files, evidence categories and checked requirements are different counts. A worksheet records application information separately. PDF/JPEG variants of one document do not represent two required categories; identical bytes deduplicate.

For example, Student identity, bank and TB evidence may show **3/4 received, 2/4 checked** while CAS is missing. The saved bank file needs CAS tuition, course length and location to calculate the required money. It remains received; missing CAS is not a reason to re-upload it. [Actual fix and model replay](finance-receipt.md).

```sh
uv run visa-agent --data data/qq-test inspect CASE_ID
uv run visa-agent --data data/qq-test trace CASE_ID
uv run visa-agent --data data/qq-test events CASE_ID
```

In Docker, prefix the command with `docker compose exec agent` and use `--data /data`. Check document names/hashes and `problems`, accepted facts, `unconfirmed_candidates`, rule `fail/unknown`, then `customer_reply`. `bank_extraction_recheck` records an omitted-field retry; it does not invent a bank name.

## Files arrive, but completion stops

| Symptom | Meaning / recovery |
|---|---|
| Sample rejected | Enable operator sample mode, then start a new thread or `/reset`; clients cannot enable it by email |
| Self-written field list | It may supply personal information, but cannot substitute for passport/bank evidence |
| Unreadable, missing page, incomplete reading | Submit a clear, complete supported document; retain the failure and page reference |
| Two different names/amounts | Both sources remain; resolve the conflict instead of overwriting a value |
| Worksheet still missing information | Fill the missing cells in column C; keep field names, use real dates and leave uncertain answers empty |
| `NEEDS_HUMAN` with HITL off | A conflict or unsupported business branch remains; disabling final approval does not implement that branch |
| `BLOCKED` | Processing failed; read the error trace, which retains the original event for investigation |
| ZIP absent at completion | Check `pack_path` and the sent MIME; packs above 18 MB remain local with an explanation |

Normal model replies are written by `Guidance.reply`. If the model/tool fails, the application preserves a non-empty service response and records the failure. That guarantees prepared content, not internet availability or successful SMTP delivery. [Recovery tests](conversation-repair.md).

## Reset and language

Reply in the same thread with `/reset` alone to start a fresh case, `/exit` to close, `/start` to reopen with a new case, or `/status` for progress. Remove signatures and attachments for commands. Reset keeps the old audit records out of the new context; it does not erase them.

The model follows the customer's Chinese or English message; worksheets and handover files are bilingual. Attachments do not select the reply language. A new email thread creates a new case even when its subject matches an older one.

## Evidence to include in a bug report

Use the [bug template](../.github/ISSUE_TEMPLATE/bug_report.yml). Include the commit, OS/native or Docker, relevant settings without secrets, the expected/actual state, and a synthetic reproduction. Privately retain run/case IDs and original traces. Public screenshots and traces must omit customer names, addresses, documents and credentials.

For a code change, run the relevant test in [TESTING.md](../TESTING.md), then the required checks in [CONTRIBUTING.md](../CONTRIBUTING.md). Repeat live model calls only when the changed model behavior needs verification; do not turn a failed response into a simulated pass.
