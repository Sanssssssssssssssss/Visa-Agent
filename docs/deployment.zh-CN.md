# 部署与日常运行

[English](deployment.md) · [邮件测试](channels/email.zh-CN.md) · [WhatsApp](channels/whatsapp.zh-CN.md)

推荐先在 Windows 跑 QQ 收件 worker。只需出站网络访问模型、IMAP 993、SMTP 465，无需公网域名、回调地址或产品页面。客户使用自己的邮箱发信。

## 1. 安装

```powershell
git clone https://github.com/Sanssssssssssssssss/Visa-Agent.git
cd Visa-Agent
uv sync --locked --python 3.12
uv run visa-agent --mode offline verify-dataset
uv run pytest -q
```

第一次需要联网下载依赖。RapidOCR 的中英文模型随锁定 wheel 安装，无需另装 GPU 或 Tesseract。Windows 和 Linux 离线检查由 CI 覆盖；真实 QQ 收发在 Windows 验证。

## 2. 配置模型

将 [.env.example](../.env.example) 复制为 `.env` 并在本机填写。各入口通过 [python-dotenv](https://bbc2.github.io/python-dotenv/) 自动加载，已设置的环境变量优先；`VISA_ENV_FILE` 可指定其他文件。更改模型或密钥后重启 worker。也可在 PowerShell 隐藏输入密钥：

```powershell
$env:VISA_MODEL = 'deepseek-flash'
$env:VISA_BASE_URL = 'https://api.deepseek.com'
$env:VISA_VISION = '1'
$credential = Read-Host 'Model API key' -AsSecureString
$env:VISA_API_KEY = [System.Net.NetworkCredential]::new('', $credential).Password
uv run python scripts/check_environment.py
```

兼容性脚本会真实调用模型并产生费用，检查普通回复、结构化输出和工具调用；图文读取另按[测试索引](../TESTING.md)运行图片案例。换模型或兼容网关后应重新检查，不能仅以普通聊天可用判定兼容。当前 DeepSeek 模型由代码关闭与强制结构化工具冲突的思考模式。后台进程继承启动终端的环境；重新开终端或重启系统后需重新提供环境变量。

## 3. 配置 Agent 邮箱

在 QQ 网页邮箱的账号与安全设置中开启 IMAP/SMTP，生成专用授权码，按[官方说明](https://help.mail.qq.com/detail/106/985)完成验证。这里使用授权码，而非网页登录密码。

```powershell
uv run python scripts/configure_qq.py
uv run python -m visa_agent.qq_mail probe
```

交互输入 Agent QQ/Foxmail 地址、允许的发件地址和授权码。**允许地址留空 = 接受所有发件人**，适合多邮箱试用。授权码通过 Windows DPAPI 加密保存；配置位于 `data/qq-test/qq-config.json`，不要提交此目录。配置时间前的邮件不自动导入，配好后再发测试邮件。

已有配置时脚本拒绝覆盖，避免重置扫描起点。要改收件策略，编辑本地 JSON 的 `accept_all` 和 `allowed_senders`；保留 `since`。切换 Agent 邮箱请用独立数据目录。

## 4. 启动、样例模式和停止

```powershell
uv run python -m visa_agent.qq_mail samples --allow-samples on
uv run python scripts/mail_service.py start --hitl off
uv run python scripts/mail_service.py status
```

Windows 也可双击 `scripts/mail-start.cmd`、`mail-status.cmd`、`mail-stop.cmd`，以及 `sample-debug-on.cmd` / `sample-debug-off.cmd`。启动脚本自动加载项目 `.env`；模型与凭证配置好后可直接双击。

`running: true` 表示持有进程锁，`last_poll.at` 是最近一次轮询。默认每 15 秒扫描一次；处理附件和等待模型时，时间戳暂不刷新，不能把一次变旧立即认定为掉线。没有新邮件时不调用模型。当前事件完成后才响应停止。

```powershell
uv run python scripts/mail_service.py stop
# 等 status 显示 running: false 后才升级或换启动参数
uv run python scripts/mail_service.py status
```

新版本通过文件锁防止同一个数据目录出现两个收件进程；不同 Agent 邮箱使用不同数据目录。网络断开按 15/30/60 秒退避，恢复后继续游标；配置、认证和程序错误仍会退出并记日志。SMTP 发送未确认时进入持久化队列，退避重试最多间隔 300 秒。容器部署见 [Docker 指南](docker.zh-CN.md)。

| 设置 | 效果 |
|---|---|
| `samples --allow-samples on/off` | 下一次轮询热加载；只影响新线程或 `/reset` 后的新案 |
| 启动 `--hitl off/on` | 清单完成后自动交付 / 等待复核；需要停进程再改，已有案保留原设置 |
| `VISA_VISION=1` | OCR 加图片；PDF 转页面图片，最多六张图，超出读取范围不能当作已检查 |
| `--request-cap N`（前台 worker） | 可选累计模型额度，默认不设上限；每事件仍最多四次请求 |

## 5. Linux 常驻部署（配置模板）

提供 [visa-agent.service](../examples/deployment/visa-agent.service) 和 [worker.env.example](../examples/deployment/worker.env.example)。本轮未在真实 Linux 主机部署 systemd；Python 路径和权限需按服务器调整。服务以单 worker 运行，持久数据必须保留。

1. 创建专用 `visa-agent` 系统用户，将仓库安装到 `/opt/visa-agent`，由该用户执行 `uv sync --locked --python 3.12`；创建该用户可写的 `/var/lib/visa-agent`。
2. 将环境样例复制为 `/etc/visa-agent.env`，填入自己的模型密钥、QQ 邮箱及授权码。建议属主 `root:visa-agent`、权限 `640`，不要放入公开仓库。
3. 首次配置时，以服务用户读取该文件，然后初始化和验证：

```sh
set -a
. /etc/visa-agent.env
set +a
cd /opt/visa-agent
.venv/bin/python scripts/configure_qq.py --from-env --accept-all --allow-samples --data /var/lib/visa-agent
.venv/bin/python -m visa_agent.qq_mail probe --data /var/lib/visa-agent
```

`--from-env` 不依赖桌面密钥环，也不把授权码写进配置 JSON。若只接受指定测试者，删掉 `--accept-all` 并填写 `VISA_QQ_ALLOWED_SENDERS`。正式材料模式删掉 `--allow-samples`；已有配置通过 `samples` 命令切换。

4. 管理员安装 service 文件，执行 `sudo systemctl daemon-reload`、`sudo systemctl enable --now visa-agent`。查看 `systemctl status visa-agent` 和 `journalctl -u visa-agent -n 30`。它会随服务器启动，异常退出后重启；人工维护使用 `sudo systemctl stop visa-agent`。

前台本机验证可执行 `python -m visa_agent.qq_mail watch --send-replies --hitl off --data <目录>`。Windows 后台脚本不会自动注册开机启动；电脑关机、休眠或未联网期间无法处理来信，恢复启动后从持久游标继续。

## 排查和升级

| 现象 | 检查位置 / 处理 |
|---|---|
| 没有回信 | `status`、本地 `worker.stdout.log` / `worker.stderr.log`；检查收件箱、发件白名单、配置时间和垃圾箱 |
| 模型或材料失败 | `visa-agent --data data/qq-test inspect <case_id>` / `trace <case_id>`，沿来源、字段、规则检查 |
| 已处理但发信不明 | SQLite `qq_receipts.send_status=retry`；按持久化退避重试，相同 Message-ID 仍可能产生重复投递 |
| 未完成 | 查看缺项和冲突；样例开关不能跳过信息、来源或可读性要求 |
| ZIP 太大 | 大于 18 MB 时不会作为附件发出，邮件说明本地已保存；当前无自动下载链接服务 |

升级前停止 worker，备份整个数据目录（含 SQLite、附件和密钥文件），再拉代码、同步锁定依赖并运行离线检查。Windows DPAPI 文件绑定原系统用户，迁移机器需重新配置授权码。规则变更会使旧审批/待发结果失效，需要重新检查案件。原始 trace 和日志含客户内容，应只在本机或授权服务器查看。
