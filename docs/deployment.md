# Deploy and operate

[简体中文](deployment.zh-CN.md) · [Email test walkthrough](channels/email.md) · [WhatsApp](channels/whatsapp.md)

The verified channel is a QQ/Foxmail inbox on Windows. It needs outbound access to the model API, IMAP 993 and SMTP 465. Customers send email; no public web server or customer UI is needed.

For a persistent container deployment, follow the [Docker guide](docker.md).

## Install and configure

```sh
git clone https://github.com/Sanssssssssssssssss/Visa-Agent.git
cd Visa-Agent
uv sync --locked --python 3.12
uv run visa-agent --mode offline verify-dataset
uv run pytest -q
```

RapidOCR includes Chinese/English models in the locked wheel. GPU and Tesseract are not required. CI checks Windows and Linux offline; real QQ delivery was verified on Windows.

Copy [.env.example](../.env.example) to `.env` and fill it locally. Entry points load it automatically with [python-dotenv](https://bbc2.github.io/python-dotenv/); existing shell variables take precedence. `VISA_ENV_FILE` selects another file. Keep credentials out of Git. Alternatively, in PowerShell:

```powershell
$env:VISA_MODEL = 'deepseek-flash'
$env:VISA_BASE_URL = 'https://api.deepseek.com'
$env:VISA_VISION = '1'
$credential = Read-Host 'Model API key' -AsSecureString
$env:VISA_API_KEY = [System.Net.NetworkCredential]::new('', $credential).Password
uv run python scripts/check_environment.py
```

The compatibility script calls the real model for plain replies, structured output and tools, and incurs usage. Run the separate image acceptance check in [TESTING](../TESTING.md) for document reading when changing providers. The current DeepSeek adapter disables thinking mode for forced structured tool output. The background worker loads the project `.env`; shell overrides are inherited when it starts. Restart after changing model/credential settings.

Enable IMAP/SMTP in your QQ account and generate its dedicated authorization code using [QQ's official instructions](https://help.mail.qq.com/detail/106/985). Then:

```sh
uv run python scripts/configure_qq.py
uv run python -m visa_agent.qq_mail probe
```

Enter the agent mailbox, allowed customer address, and code. Leave the customer address blank to accept any sender. Windows stores the code using DPAPI; local settings are in `data/qq-test/qq-config.json`. Send test messages **after setup**; earlier messages are excluded by its start timestamp. `probe` verifies IMAP/SMTP login without sending a message.

Setup refuses to overwrite existing configuration. Edit `accept_all` and `allowed_senders` locally without resetting `since`; use a separate data directory for another agent mailbox.

## Run in the background

```sh
uv run python -m visa_agent.qq_mail samples --allow-samples on
uv run python scripts/mail_service.py start --hitl off
uv run python scripts/mail_service.py status
uv run python scripts/mail_service.py stop
```

Windows shortcuts live in `scripts/mail-{start,status,stop}.cmd` and `sample-debug-{on,off}.cmd`. The shortcuts also load the project `.env`, so configured deployments can start by double-clicking.

`running: true` means the OS lock is held. `last_poll.at` records the last completed poll; document/model processing can delay its update. Polling defaults to 15 seconds. Idle polls do not call the model. Stop waits for the current event; confirm `running: false` before upgrading.

One lock prevents duplicate workers for one data directory. Transient network failures back off at 15/30/60 seconds and continue from the cursor after recovery. Configuration, authentication and programming failures exit with a diagnostic; unconfirmed SMTP sends persist with retry backoff up to 300 seconds.

| Setting | Meaning |
|---|---|
| `samples --allow-samples on/off` | Reloaded next poll; new or reset cases only |
| `start --hitl off/on` | Automatic checklist completion / independent review; restart to change, existing cases retain their setting |
| `VISA_VISION=1` | OCR plus images/rendered PDF pages; six-image limit, unread content is not treated as checked |
| `watch --request-cap N` | Optional cumulative cap; unset by default, four-request limit per event remains |

The Windows helper does not install a boot service. Processing requires an awake, connected machine. Restart resumes persistent state after a shutdown.

## Linux systemd template

[visa-agent.service](../examples/deployment/visa-agent.service) and [worker.env.example](../examples/deployment/worker.env.example) provide a server template. **A real systemd host deployment was not run in this release.** Adapt paths and permissions before use.

1. Create a dedicated `visa-agent` OS user; install the checkout and its locked environment under `/opt/visa-agent`. Make `/var/lib/visa-agent` writable by that user.
2. Copy the environment example to `/etc/visa-agent.env`, fill in your model and mail credentials, and restrict it, for example owner `root:visa-agent`, mode `640`.
3. As the service user, load the private file and initialize once:

```sh
set -a
. /etc/visa-agent.env
set +a
cd /opt/visa-agent
.venv/bin/python scripts/configure_qq.py --from-env --accept-all --allow-samples --data /var/lib/visa-agent
.venv/bin/python -m visa_agent.qq_mail probe --data /var/lib/visa-agent
```

Environment mode avoids a desktop keyring and does not save credentials into JSON. For restricted intake, omit `--accept-all` and configure `VISA_QQ_ALLOWED_SENDERS`. Omit `--allow-samples` for normal material checks. Existing settings can be changed with the `samples` command.

4. As administrator, install the service file, then run `sudo systemctl daemon-reload` and `sudo systemctl enable --now visa-agent`. Inspect `systemctl status visa-agent` and `journalctl -u visa-agent -n 30`. Stop for maintenance with `sudo systemctl stop visa-agent`.

To inspect foreground operation: `python -m visa_agent.qq_mail watch --send-replies --hitl off --data <directory>`. Keep one persistent data directory per mailbox.

## Troubleshoot and upgrade

| Symptom | Inspect |
|---|---|
| No reply | Worker status/logs, INBOX, sender policy, start timestamp and spam folder |
| Model/material failure | `visa-agent --data data/qq-test inspect <case_id>` and `trace <case_id>` |
| Unknown delivery | `qq_receipts.send_status=retry`; persisted backoff retries with the same Message-ID (duplicates remain possible) |
| Incomplete case | Missing facts, conflicts or unreadable documents; sample mode does not bypass these |
| Oversized ZIP | Above 18 MB the reply explains it was saved locally, not emailed; no hosted download link exists |

Stop the worker and back up the **whole** data directory before upgrades. Synchronize the lockfile, run offline checks, then restart. DPAPI credentials require the original Windows user/machine; configure a fresh code when migrating. Rule changes invalidate old approvals and pending replies. Raw traces/mail logs contain customer content and should stay local or on an authorized server.
