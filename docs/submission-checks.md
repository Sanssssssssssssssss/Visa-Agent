# Public submission checks / 公开提交检查

2026-10-07 · Windows / Python 3.12. This release reorganizes presentation and makes the email worker easier to operate. It does not re-score the model or claim a new live visa case.

## Executed locally / 本机实际执行

| Check | Result |
|---|---|
| Full offline suite | **217 passed, 79.57 seconds** |
| Ruff | Passed |
| Frozen dataset verification | Passed; `778242984890a6c7314eb52a3f84cfdbf7d94b1e7bf3afd1ba32802768ebf9a2` |
| README Visitor replay in an isolated directory | Passed; `COMPLETE`, ZIP produced, zero real model requests |
| Worker process controls | New background process started; second start retained the same process |
| Real QQ login | IMAP and SMTP passed; probe sent no email |
| Background polling | Fresh completed poll observed, sample mode on, HITL off |
| Documentation images | Rendered and visually inspected transcript figure and actual ZIP entry page |
| Privacy scan before publication | Current tracked files and reachable Git objects checked for current credentials, personal test mailboxes and common credential formats; no matches |

Four new offline operational tests cover a real cross-process lock and abrupt exit, five simulated network failures followed by recovery, status without reading credentials/customer text, and environment-based setup without storing the mail secret. The first lock test incorrectly terminated Windows' virtualenv launcher instead of the Python owner; it was corrected to exit inside the lock-owning process, then the full suite passed. No live network outage was deliberately induced.

这轮业务模型 API 新增请求为 **0**。QQ 登录探测和空轮询不调用模型；新 Logo 使用了一次独立图片生成。已有真实邮件和图片识别成绩继续保留其原输入、版本及局限，见 [TESTING](../TESTING.md)。

## Submission contents / 提交内容

- English/Chinese README, architecture, deployment and channel guides; the user switches through links, while replies follow the message language.
- Project logo; real transcript excerpts clearly labelled as a figure; actual generated pack screenshot.
- Nine early reports moved into `docs/history/`. Eight complete synthetic trace files removed from the current tree after a local backup. Brief receipts, failures, fixtures and sample packs retained.
- Current credentials, customer mail, local data, logs and third-party downloads remain ignored. The scan is a targeted publication check, not a comprehensive security audit.
- Worker start/stop/status, local single-process lock, network backoff, headless environment credentials and a systemd template. Runtime dependencies are unchanged.

## Verification boundaries / 边界

The [CI workflow](https://github.com/Sanssssssssssssssss/Visa-Agent/actions/workflows/ci.yml) runs lockfile install, Ruff, dataset checks, tests and local documentation links on Windows and Linux. Use the run matching the reviewed commit; a historical green badge is not a receipt for a newer change.

The real mailbox worker was validated on this Windows host. The Linux systemd service is a template and was not deployed to a server. WhatsApp remains a simulator plus a documented Chatwoot integration path; no live WhatsApp provider test is claimed. A running local worker needs an awake, connected machine and correctly configured credentials.
