# Test by sending email

[简体中文](email.zh-CN.md) · [Deployment](../deployment.md) · [Actual transcripts](../full-delivery-transcripts.md)

Complete setup and check worker status first. Send from a separate customer mailbox to **your configured agent QQ address**. There is no hosted public inbox. Enable sample mode and disable HITL for the synthetic walkthrough.

## First contact

Use any subject, for example `Visa test - Visitor`:

```text
Hello, I would like to visit the UK. This is my first application. Where should I start?
```

Expect a reply in English, next questions and progress. Once the route is known, a bilingual worksheet is attached. Fill column C and preserve field names. Leave uncertain answers empty; “unknown” must not become “no”. Delay includes polling (15 seconds), OCR and model processing.

## Complete each route

Start a separate thread for each applicant/route. Use your mail client's **Reply** for follow-ups. All these fixtures are synthetic and marked for testing.

| Route | Second email: worksheet + identity | Third email: remaining attachments |
|---|---|---|
| Visitor | `datasets/intake/visitor-example-TEST-ONLY.xlsx`; `datasets/formatted-materials-v2/visitor/identity.jpg` | Same folder: `funds-scan.pdf`, `work.jpg` |
| Student | `datasets/intake/student-example-TEST-ONLY.xlsx`; `datasets/formatted-materials-v2/student/identity.jpg` | Same folder: `funds-scan.pdf`, `school.jpg`, `health.jpg` |
| Skilled Worker | `datasets/intake/skilled_worker-example-TEST-ONLY.xlsx`; `datasets/formatted-materials-v2/skilled_worker/identity.jpg` | Same folder: `sponsor.jpg`, `language.jpg`, `health.jpg` |

For Student, introduce the course offer in the first email. For Skilled Worker, introduce the UK job offer. Say “I have filled in the worksheet and attached my passport” in the second email and “Here are the remaining documents. Is anything still missing?” in the third. Select one format per document; do not mix applicants or upload all PDF/JPEG variants.

Expected progression: `WAIT_USER` to `COMPLETE`, followed by a `visa-materials.zip` attachment. Unzip it, open `START-HERE.html`, and inspect originals, worksheet, provenance and the GOV.UK handover. A live model can still fail extraction; retain the actual failure rather than treating this expected result as a pass.

Visitor/Worker image fixtures have real API receipts; Student was verified against the same content in the first layout version, not rerun in v2. The three complete **real mailbox** journeys used earlier text PDFs. [Coverage details](../full-delivery.md).

For a quick Visitor test, send the worksheet and its three image/scan attachments in one new message. The same four files were tested through real mail with sample mode ON (complete) and OFF (waiting). [Receipt](../sample-switch.md).

## Different senders and negative cases

| Action | Expected behavior |
|---|---|
| Another mailbox sends a new message | Separate case, no previous customer's facts |
| Same customer replies | Same case and collected documents |
| Same customer starts a new thread | New case, even with the same subject |
| Different customer takes over an existing thread | Sender mismatch is rejected |
| `/status` | Progress without a model call |
| `/reset` | Fresh case; old records retained; current sample policy applies |
| `/exit`, then more documents | Closed conversation; `/start` opens a new case |
| `datasets/intake/bad-missing-birthday.xlsx` | Missing date of birth prevents completion |
| `bad-passport-conflict.xlsx` with inconsistent identity | Conflict remains visible |
| `datasets/document-quality/personal-notes.pdf` or `passport-notes.jpg` | Self-report cannot satisfy passport evidence |
| Full sample documents in a fresh normal-mode case | Ask for real evidence, no completed ZIP |

Send commands alone, without a signature or attachments. Attach files using the mail attachment control; inline/signature images are not application evidence. Limits: five attachments per event, 10 MB per file, 20 PDF pages and 25 MB per email.

## Inspect each response

```sh
uv run visa-agent --data data/qq-test inspect <case_id>
uv run visa-agent --data data/qq-test trace <case_id>
uv run visa-agent --data data/qq-test events <case_id>
```

Find IDs in `qq-watch-last.json` or `worker.stdout.log`. Actual sent MIME lives in `qq-previews/*.sent.eml`. Traces include proposals, guidance, quotes, checks and the final reply. Do not publish traces containing customer data.

Address syntax, thread binding and mailbox login do not authenticate the human sender. The connector does not implement complete sender-domain authentication. Open intake is intended for a controlled pilot; the operator pays model usage.
