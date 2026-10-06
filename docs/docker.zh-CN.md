# Docker 部署

[English](docker.md) · [Windows 原生启动](deployment.zh-CN.md) · [发邮件亲测](channels/email.zh-CN.md)

使用 Docker Engine/Desktop、Compose **2.24+** 和 Linux 容器。已验证镜像面向 amd64。服务只需访问模型 HTTPS、IMAP 993、SMTP 465，不开放网页端口。可先分配 2 核/4 GB，再按实际材料页数和延迟调整。

## 配置与启动

```sh
git clone https://github.com/Sanssssssssssssssss/Visa-Agent.git
cd Visa-Agent
cp .env.example .env
```

Windows 用 `Copy-Item .env.example .env`。在本机填写自己的模型密钥、Agent QQ/Foxmail 邮箱及授权码。要体验仓库里的样例和已填表格，可设置：

已有 `.env` 时直接编辑，避免覆盖现有密钥和配置。

```dotenv
VISA_API_KEY=你的模型密钥
VISA_QQ_MAILBOX=123456@qq.com
VISA_QQ_AUTH_CODE=你的16位授权码
VISA_QQ_ACCEPT_ALL=1
VISA_QQ_ALLOW_SAMPLES=1
VISA_HITL=off
VISA_MAIL_INTERVAL=15
```

`ACCEPT_ALL=1` 允许不同客户邮箱写信。限制测试者时改为 `0`，填写 `VISA_QQ_ALLOWED_SENDERS`。样例模式供合成材料调试，正式材料设为 `0`。Linux 的 `.env` 建议权限 `600`。**同一邮箱只运行一个收件 worker；迁到 Docker 前先停止原生 worker。**

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail 30 agent
```

首次启动创建 `/data/qq-config.json`，重启保留原扫描起点、收件策略和游标；配置启动后再发测试邮件。新邮件线程建案，回复沿用原线程。[两步补件的已填表格及附件](channels/email.zh-CN.md)可以直接用。

进程使用 UID `10001`；案件、SQLite、原始附件、邮件和 ZIP 放在持久数据卷，`/backups` 使用独立卷。镜像不包含本机 `.env`、客户资料和私有 trace；根文件系统只读。运行日志含客户内容，应留在授权机器。

## 状态、启停与切换

```sh
docker compose exec agent python -m visa_agent.qq_mail status --data /data
docker compose exec agent python -m visa_agent.qq_mail probe --data /data
docker compose exec agent visa-agent --data /data inspect CASE_ID
docker compose exec agent visa-agent --data /data trace CASE_ID
docker compose exec agent python -m visa_agent.qq_mail samples --allow-samples off --data /data
docker compose stop agent
docker compose start agent
```

健康检查只读本地进程锁和轮询时间，不调用模型。长材料处理会推迟时间戳。SIGTERM 在当前邮件保存/发送后退出，未处理游标保留；Compose 最多等待十分钟。重启继续原案件和待发队列，SMTP 结果不明时重试仍可能重复。

更改模型、密钥或 HITL 环境后执行 `docker compose up -d --force-recreate`。已有案件保留创建时策略，新线程或 `/reset` 才使用新的 HITL/样例策略。`docker compose down` 保留卷；**`down -v` 会删除案件及备份卷。**

## 备份与恢复

先停 worker 和其他写入者。使用未用过的备份名及容器名：

```sh
docker compose stop agent
docker compose run --name visa-agent-backup --no-deps agent python scripts/manage_data.py backup --data /data --archive /backups/cases-20261007.tar.gz
mkdir -p backups
docker cp visa-agent-backup:/backups/cases-20261007.tar.gz ./backups/
docker rm visa-agent-backup
docker compose start agent
```

Windows 可用 `New-Item -ItemType Directory -Force backups`。备份带文件哈希清单，工具拒绝占用中的 worker、覆盖备份、危险归档路径或覆盖已有案件。恢复采用同一绝对数据路径；Docker 在另一台机器仍挂载 `/data`。Windows DPAPI 授权码不适用于 Linux，需通过环境或 secret 文件提供。

新机器的空数据卷可这样恢复：

```sh
docker compose create agent
docker compose cp ./backups/cases-20261007.tar.gz agent:/backups/restore.tar.gz
docker compose run --rm --no-deps --user 0 agent python scripts/manage_data.py restore --data /data --archive /backups/restore.tar.gz
docker compose up -d
```

已有部署用独立空卷恢复，保留旧卷。已验证整目录恢复；Windows 案件绝对路径自动迁到 Linux 尚未实现。

## 升级

先备份、停 worker，再 `git pull`、`docker compose build --pull agent`、`docker compose up -d`。卷中的案件保留；规则变化会在重处理时使旧批准/结果失效。回滚使用保留的旧镜像和备份，启动报错不要通过删卷解决。

## 可选 secrets

将模型密钥、QQ 授权码分别写入被忽略的 `secrets/model_key.txt`、`secrets/qq_code.txt`，从 `.env` 删除对应明文；邮箱和策略留在 `.env`。Linux 文件可设为 `root:10001`、权限 `640`，让服务组能读。

```sh
docker compose -f compose.yaml -f compose.secrets.yaml up -d --build
```

`VISA_API_KEY_FILE` 和 `VISA_QQ_AUTH_CODE_FILE` 读取挂载文件。原生部署中非空环境值优先；这个 Compose override 会主动清空明文值。

## 容器验收与发布

[容器 CI](../.github/workflows/container.yml)实际构建 runtime/test 镜像，验证普通用户、OCR/扫描 PDF、三路线离线 ZIP、恢复、重复初始化、健康检查及 SIGTERM，再跑回归套件。它不使用真实模型密钥或邮箱。

[publish-container](../.github/workflows/publish-container.yml) 可手动运行：构建及离线验收后，推送 `latest` 和 `sha-COMMIT` 到 GHCR。公开可见性在 GitHub Packages 设置；它不配置你的生产邮箱。[实际验收与边界](container-acceptance.md)。

依据：[Compose 环境配置](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/)、[服务定义](https://docs.docker.com/reference/compose-file/services/)、[uv 容器说明](https://docs.astral.sh/uv/guides/integration/docker/)。
