# Tests and evidence / 测试索引

[English README](README.md) · [中文入口](README.zh-CN.md) · [Manual email walkthrough](docs/channels/email.zh-CN.md)

Offline tests check mechanisms; real API runs check recorded model behavior; mailbox/download receipts check delivery. A negative case passes when it stops at the expected blocker. None of these establishes document authenticity or visa eligibility.

离线、真实模型、真实收发分别计数。反例的“通过”是正确阻止完成；不能用成功发送邮件代替业务完成。

## Run / 运行

```sh
uv sync --locked --python 3.12
uv run ruff check src tests scripts
uv run visa-agent --mode offline verify-dataset
uv run pytest -q
uv run python scripts/check_docs.py
```

`tests/conftest.py` disables real model requests and local `.env` loading. CI runs these checks on Windows and Linux. Latest model replies, fault delivery and configuration results: [conversation-repair.md](docs/conversation-repair.md). Earlier submission results are in [submission-checks.md](docs/submission-checks.md); counts belong to their recorded revisions.

| Area / 能力 | Protection / 检查 | Test file |
|---|---|---|
| Route checks / 业务规则 | Three routes, unknown conditions, missing evidence, stale approvals | [cases](tests/test_cases.py), [boundaries](tests/test_boundaries.py), [HITL](tests/test_hitl.py) |
| Reading / 读取 | Mixed PDFs, masked content, page gaps and low quality | [mixed PDF](tests/test_mixed_pdf.py), [bad cases](tests/test_bad_case_regressions.py), [public images](tests/test_public_image_regressions.py) |
| Evidence / 材料 | Self-report rejection, samples, classification and sources | [document quality](tests/test_document_quality.py), [sample switch](tests/test_sample_switch.py) |
| Application information / 填表 | Missing dates, formulas, invalid values and contradictions | [intake](tests/test_intake.py) |
| Customer guidance / 引导 | Valid question IDs, language, progress and failure wording | [guidance](tests/test_guidance.py), [replies](tests/test_reply_regressions.py), [service](tests/test_customer_service.py) |
| Channels / 渠道 | MIME, reference chains, deduplication, stale/ambiguous sending | [QQ](tests/test_qq_mail.py), [Graph](tests/test_outlook.py) |
| Persistence / 隔离与恢复 | 4 interleaved sender/account identities × 30 logical days × 3 repetitions × HITL on/off | [inbox](tests/test_inbox.py) |
| Worker / 后台 | OS lock across processes, abrupt exit, 5 network failures then recovery, headless credentials | [worker](tests/test_worker.py) |
| Pack / 交付 | ZIP file set, hashes, worksheet and bilingual handover | [delivery](tests/test_delivery_handover.py) |

The 30-day test advances timestamps; it is not a month of real uptime. Concurrency uses the current serialized SQLite engine and does not establish production capacity.

## Live receipts / 真实记录

| Experiment | Actual result | Usage / 用量 |
|---|---|---|
| [Three-route delivery](docs/full-delivery.md) | 3 × 3 real emails, ZIPs downloaded and compared; synthetic applicants | 15 model calls for provider journeys; API reruns and negative cases separately recorded |
| [Material acceptance](docs/document-quality.md) | Original false-completion reproduced; final 5 negative inputs blocked, earlier failures retained | 60 calls across the investigation, including failures |
| [Sample mode ON/OFF](docs/sample-switch.md) | Same 4 input files: ON complete + received ZIP; OFF waiting, no ZIP | 3 calls, 17,528 input / 1,965 output tokens |
| [Earlier experiments](docs/history/README.md) | OCR, adversarial inputs, session and customer-service failures/reruns | Per-report usage; do not combine overlapping runs |

No prices were configured for these receipts; usage is reported without an invented cost. Real third-party bank samples test parsing only; their licensing/source links live in [public-images.md](docs/public-images.md).

## Reproduce model checks / 真实 API 复跑

Configure credentials as in the [deployment guide](docs/deployment.md), then use a separate data/output directory. These commands incur real API usage.

```sh
uv run python scripts/check_environment.py
uv run visa-agent --data data/my-acceptance --mode live accept --output output/my-acceptance
uv run python scripts/full_delivery_acceptance.py --output output/my-images --formatted --materials datasets/formatted-materials-v2
uv run python scripts/document_quality_acceptance.py --help
```

The compatibility script checks plain replies and structured tool calls; use the image acceptance runner for actual OCR/vision. CLI acceptance uses fixed customer events and scripted adviser decisions. The image runner calls the model but does **not** send real email. For mailbox transport, follow the [email guide](docs/channels/email.md) and confirm replies/ZIP in the customer's inbox.

Frozen datasets and expected results are under [datasets/](datasets/). Do not regenerate them to hide a failure. Keep full raw traces, customer data and credentials local; commit only synthetic fixtures, concise receipts, reproducible commands and known limitations.
