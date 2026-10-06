# Configuration reference

[简体中文](configuration.zh-CN.md) · [Docker](docker.md) · [Native deployment](deployment.md) · [Troubleshooting](troubleshooting.md)

Copy [.env.example](../.env.example) to a private `.env`. Startup loads it from the working directory; already-set environment variables take priority. `VISA_ENV_FILE` selects another file. The Windows background helper explicitly loads the project file. Do not commit actual keys, mailbox credentials or customer storage.

## Model and case policy

| Variable | Example/default | Meaning |
|---|---|---|
| `VISA_MODEL` | `deepseek-flash` | Model name sent to your configured provider |
| `VISA_BASE_URL` | `https://api.deepseek.com` | OpenAI-compatible endpoint; changed providers need compatibility testing |
| `VISA_API_KEY` | Required for live mode | Model credential; existing `DEEPSEEK_API_KEY` is also supported |
| `VISA_API_KEY_FILE` | Empty | UTF-8 secret file used when the literal key is empty |
| `VISA_VISION` | `1` | Send OCR plus original images/rendered PDF pages; `0` selects text-only input |
| `VISA_HITL` | `off` in the example/Compose | Automatic checklist completion; `on` requires independent review |
| `VISA_DATA_DIR` | `data` | CLI case storage; Compose overrides it to `/data` |
| `VISA_INPUT_USD_PER_MILLION` / `VISA_OUTPUT_USD_PER_MILLION` | Empty | Optional token prices; unset prices produce usage without a cost estimate |

The bare application API defaults to HITL on if no setting is provided. Email helpers and the provided deployment configuration default to off. Set the value explicitly so your intended policy is clear. Existing cases retain their HITL/sample policy; use a new thread or `/reset` after changing it.

## Email intake

| Variable | Example/default | Meaning |
|---|---|---|
| `VISA_QQ_MAILBOX` | Required | Agent QQ/Foxmail inbox; customers may use any email provider |
| `VISA_QQ_AUTH_CODE` | Required for headless deployment | QQ IMAP/SMTP authorization code, not the web password |
| `VISA_QQ_AUTH_CODE_FILE` | Empty | Secret file alternative; literal values take priority |
| `VISA_QQ_DATA_DIR` | `data/qq-test` | Native mailbox storage; Compose overrides it to `/data` |
| `VISA_MAIL_INTERVAL` | `15` | Seconds between polls; minimum 10; OCR/model work adds processing time |
| `VISA_QQ_ACCEPT_ALL` | **`1`** | New inbox accepts every customer address with any subject |
| `VISA_QQ_ALLOWED_SENDERS` | Empty | Used only when explicitly setting `ACCEPT_ALL=0` |
| `VISA_QQ_ALLOW_SAMPLES` | `0` | New cases reject test samples as normal evidence; set `1` for a synthetic walkthrough |

An open inbox needs no sender registration or `[VisaTest]` subject. New threads create separate cases. Reply continues the original sender's case; another sender cannot take it over. Self-mail, automatic replies and provider notices are filtered to prevent loops. Syntactically valid email headers are not proof of the sender's identity.

### What takes effect when?

`configure_qq.py --from-env` saves intake settings to `qq-config.json` on first boot. Existing configuration is preserved, including its original `since` timestamp. **Changing `.env` does not replace an existing inbox's intake policy.**

| Change | Apply it |
|---|---|
| Model key/name/endpoint, vision, interval | Restart the native worker; with Docker, recreate it using `docker compose up -d --force-recreate` |
| HITL | Restart with the chosen policy; start/reset a case |
| Sample mode | `python -m visa_agent.qq_mail samples --allow-samples on/off`; loaded next poll, affects new/reset cases |
| Existing sender policy | Edit only `accept_all`, `allowed_senders`, `require_tag` in the saved JSON; next poll reloads it |
| Agent mailbox | Use a separate data directory/volume |

For an existing inbox to accept everyone, save these fields while preserving all other configuration, especially `mailbox` and `since`:

```json
{
  "accept_all": true,
  "allowed_senders": [],
  "require_tag": false
}
```

This is a partial edit, not a replacement configuration. For a manual edit, stop the worker first to avoid a partially written JSON file being read. Docker operators can create the ignored `backups/` directory, use `docker compose cp agent:/data/qq-config.json ./backups/qq-config.local.json`, edit that private copy, then copy it back with `docker compose cp ./backups/qq-config.local.json agent:/data/qq-config.json` and `docker compose start agent`. Keep the copy private. Do not delete the database or reset scan time to change an allowlist.

## Limits and optional pilot settings

| Limit | Current behavior |
|---|---|
| Input | Five attachments/event; 10 MB/file; 20 PDF pages; 25 MB/email |
| Working context | Up to 20 recent full turns; 32,000 characters; essential state is retained or processing stops |
| Model work | Four HTTP requests/event shared by extraction, tools, retries and reply; no cumulative cap by default |
| Visual input | Up to six images/pages; unread content cannot be assumed checked |
| Emailed ZIP | Above 18 MB, saved locally with an explanation instead of an attachment |

`watch --request-cap N` is an optional cumulative cap. These implementation bounds are not `.env` tunables; see [architecture](architecture.md) before modifying them.

`VISA_MS_CLIENT_ID`, `VISA_MS_TENANT`, `VISA_OUTLOOK_MAILBOX` and `VISA_OUTLOOK_ALLOW_SENDERS` belong to the separate Outlook Graph pilot. QQ setup does not need them. Graph live OAuth was not verified; WhatsApp has an integration guide and simulator only.

[Docker secret mounting](docker.md#optional-docker-secrets) clears literal keys in its override. Native Windows interactive setup stores the QQ code with DPAPI; that encrypted file cannot be moved to Linux. Headless setup saves no credential into the intake JSON.
