# Docker deployment

[简体中文](docker.zh-CN.md) · [Native Windows setup](deployment.md) · [Configuration](configuration.md) · [Troubleshooting](troubleshooting.md)

Use Docker Engine/Desktop with Compose **2.24 or newer**, Linux containers, and an amd64 CPU for the verified image. The worker needs outbound model HTTPS, IMAP 993 and SMTP 465. It exposes no public application port. A 2-core/4 GB machine is a practical starting allocation; actual document workload affects memory and latency.

## Configure and start

```sh
git clone https://github.com/Sanssssssssssssssss/Visa-Agent.git
cd Visa-Agent
cp .env.example .env
```

Windows: `Copy-Item .env.example .env`. Fill your own model key, agent QQ/Foxmail address and mailbox authorization code. For a synthetic walkthrough, configure:

If `.env` already exists, edit it instead of overwriting the configured values.

```dotenv
VISA_API_KEY=your-model-key
VISA_QQ_MAILBOX=123456@qq.com
VISA_QQ_AUTH_CODE=your-16-letter-code
VISA_QQ_ACCEPT_ALL=1
VISA_QQ_ALLOW_SAMPLES=1
VISA_HITL=off
VISA_MAIL_INTERVAL=15
```

`ACCEPT_ALL=1` permits any sender. For restricted intake, set it to `0` and fill `VISA_QQ_ALLOWED_SENDERS`. Sample mode is for the labelled test documents; use `0` for normal material checks. Keep `.env` private (`chmod 600 .env` on Linux). Run one active worker per mailbox; stop an existing native worker before moving that mailbox to Docker.

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail 30 agent
```

First boot creates `/data/qq-config.json`; later boots preserve its original scan start, sender settings and cursor. Changing `.env` does not overwrite an existing allowlist; use the [saved policy instructions](configuration.md#what-takes-effect-when). Send your first email after startup. New threads create cases; Reply continues the existing case. [Pre-filled worksheets and attachments](channels/email.md#complete-each-route) let you test without filling the form again.

The process runs as UID `10001`. Named volumes persist SQLite, raw messages, attachments, traces and packs; `/backups` has a separate volume. Image builds exclude `.env`, local customer data and private traces. The root filesystem is read-only. Logs may contain customer content and belong on the operator's machine.

## Check, stop and resume

```sh
docker compose exec agent python -m visa_agent.qq_mail status --data /data
docker compose exec agent python -m visa_agent.qq_mail probe --data /data
docker compose exec agent visa-agent --data /data inspect CASE_ID
docker compose exec agent visa-agent --data /data trace CASE_ID
docker compose exec agent python -m visa_agent.qq_mail samples --allow-samples off --data /data
docker compose stop agent
docker compose start agent
```

Health checks inspect the local lock and recent poll timestamp without calling the model. A long OCR/model turn can delay the timestamp. SIGTERM finishes the current message and preserves the unprocessed cursor; Compose allows up to ten minutes before forced termination. Pending input and mail attempts persist across restart. SMTP retry can duplicate an ambiguously accepted message.

Changing model credentials/HITL environment requires `docker compose up -d --force-recreate`. Existing cases keep their HITL/sample policy; a new thread or `/reset` gets the current policy. `docker compose down` preserves named volumes. **`down -v` deletes case and backup volumes.**

## Backup and restore

Stop the worker and other writers first. Use a unique backup filename and container name:

```sh
docker compose stop agent
docker compose run --name visa-agent-backup --no-deps agent python scripts/manage_data.py backup --data /data --archive /backups/cases-20261007.tar.gz
mkdir -p backups
docker cp visa-agent-backup:/backups/cases-20261007.tar.gz ./backups/
docker rm visa-agent-backup
docker compose start agent
```

The backup includes a file/hash manifest. The CLI refuses an active worker, overwriting an archive, unsafe archive members or restoring over existing case data. Restore uses the same absolute data path; Docker keeps that path `/data` on any host. Windows DPAPI credentials cannot be reused on Linux; supply the QQ code via environment or a secret file.

On a fresh Docker data volume:

```sh
docker compose create agent
docker compose cp ./backups/cases-20261007.tar.gz agent:/backups/restore.tar.gz
docker compose run --rm --no-deps --user 0 agent python scripts/manage_data.py restore --data /data --archive /backups/restore.tar.gz
docker compose up -d
```

An existing deployment needs a separate, empty volume for restore, preserving the old one. Whole-directory restore is tested; automatic migration of Windows absolute case paths into Linux is not implemented.

## Upgrade

Back up before upgrading. Stop the worker, `git pull`, then `docker compose build --pull agent` and `docker compose up -d`. Persistent cases remain in the volume. Changed rules invalidate old approvals/results on reprocessing. Retain a previous image tag and backup for rollback; do not delete the volume to resolve a startup error.

## Optional Docker secrets

Put the model key and QQ authorization code in ignored `secrets/model_key.txt` and `secrets/qq_code.txt`; remove their literal values from `.env`. Keep `VISA_QQ_MAILBOX` and policy there. On Linux, give the service group read access, for example owner `root:10001`, mode `640`, on both secret files.

```sh
docker compose -f compose.yaml -f compose.secrets.yaml up -d --build
```

`VISA_API_KEY_FILE` and `VISA_QQ_AUTH_CODE_FILE` load the mounted files. Existing non-empty environment values take priority in native deployments; the secrets override deliberately clears literal values.

## Image validation and publication

[Container CI](../.github/workflows/container.yml) builds runtime and test images, checks non-root OCR/scan reading, three-route offline ZIP delivery, restoration, repeated initialization, health and graceful SIGTERM, then runs the regression suite. It uses no model keys or live mailbox.

[publish-container](../.github/workflows/publish-container.yml) is a manual GitHub Actions workflow: build, offline acceptance, then push `latest` and `sha-COMMIT` to GHCR. Package visibility is configured in GitHub Packages; the workflow does not configure your production inbox. The verified build/platform and limits are recorded in [container acceptance](container-acceptance.md).

References: [Compose environment configuration](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/), [Compose service settings](https://docs.docker.com/reference/compose-file/services/), [uv image guidance](https://docs.astral.sh/uv/guides/integration/docker/).
