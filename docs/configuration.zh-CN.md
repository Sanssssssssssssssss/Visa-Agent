# 配置参考

[English](configuration.md) · [Docker 部署](docker.zh-CN.md) · [本机部署](deployment.zh-CN.md) · [故障排查](troubleshooting.zh-CN.md)

将 [.env.example](../.env.example) 复制为私有 `.env`。入口从当前工作目录加载，已设置的环境变量优先；`VISA_ENV_FILE` 可指定其他文件。Windows 后台脚本明确读取项目里的文件。实际密钥、授权码和客户存储目录不要提交。

## 模型与案件设置

| 变量 | 示例/默认值 | 用途 |
|---|---|---|
| `VISA_MODEL` | `deepseek-flash` | 供应商接受的模型名称 |
| `VISA_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容接口；换供应商需重跑兼容性检查 |
| `VISA_API_KEY` | 真实调用必填 | 模型密钥，也支持已有的 `DEEPSEEK_API_KEY` |
| `VISA_API_KEY_FILE` | 空 | 字面密钥为空时读取 UTF-8 私有文件 |
| `VISA_VISION` | `1` | 同时发送 OCR 与原图/PDF 页面图；`0` 为纯文本 |
| `VISA_HITL` | 示例和 Compose 为 `off` | 清单完成后自动交付；`on` 等独立人工复核 |
| `VISA_DATA_DIR` | `data` | CLI 案件目录；Compose 覆盖为 `/data` |
| `VISA_INPUT_USD_PER_MILLION` / `VISA_OUTPUT_USD_PER_MILLION` | 空 | 可选 token 单价；没配置则只记用量，不估费用 |

裸应用 API 未传设置时默认 HITL 开启；邮件脚本和提供的部署示例默认关闭。请显式配置。已有案件保留创建时的 HITL/样例策略，改完后用新线程或 `/reset` 新建案件。

## 邮箱收件

| 变量 | 示例/默认值 | 用途 |
|---|---|---|
| `VISA_QQ_MAILBOX` | 必填 | Agent QQ/Foxmail 邮箱；客户可用任意邮箱服务商 |
| `VISA_QQ_AUTH_CODE` | 无交互部署必填 | QQ IMAP/SMTP 专用授权码，不是网页登录密码 |
| `VISA_QQ_AUTH_CODE_FILE` | 空 | 私有文件替代；非空字面值优先 |
| `VISA_QQ_DATA_DIR` | `data/qq-test` | 本机邮箱数据目录；Compose 覆盖为 `/data` |
| `VISA_MAIL_INTERVAL` | `15` | 两次轮询间隔，最小 10 秒；另加 OCR 和模型耗时 |
| `VISA_QQ_ACCEPT_ALL` | **`1`** | 新邮箱接受任意客户地址和主题 |
| `VISA_QQ_ALLOWED_SENDERS` | 空 | 只有显式设 `ACCEPT_ALL=0` 才用于限制地址 |
| `VISA_QQ_ALLOW_SAMPLES` | `0` | 普通案件拒绝样例充当正式证明；合成演示设 `1` |

开放收件不需要登记客户地址，也不要求主题带 `[VisaTest]`。新线程建独立案件，原发件人在原线程回复继续原案；换邮箱不能接管别人的案件。自发邮件、自动回信和服务商通知会被过滤，避免循环。有效邮件头不能证明客户身份。

### 修改何时生效

首次 `configure_qq.py --from-env` 会把收件策略存入 `qq-config.json`；重启保留它与原来的 `since` 扫描起点。**已有邮箱的收件策略不会被 `.env` 覆盖。**

| 修改 | 操作 |
|---|---|
| 模型名称/密钥/接口、视觉输入、轮询间隔 | 重启本机 worker；Docker 用 `docker compose up -d --force-recreate` 重建进程 |
| HITL | 按新策略重启，再新建或重置案件 |
| 样例模式 | `python -m visa_agent.qq_mail samples --allow-samples on/off`，下轮加载，影响新案和重置后的案 |
| 已有收件策略 | 只改 JSON 的 `accept_all`、`allowed_senders`、`require_tag`，下轮加载 |
| Agent 邮箱 | 换独立数据目录或 volume |

让已有邮箱开放收件时，只修改以下字段，保留其余内容，尤其是 `mailbox` 和 `since`：

```json
{
  "accept_all": true,
  "allowed_senders": [],
  "require_tag": false
}
```

这是局部修改，不能用这三项覆盖整个配置。手动编辑前先停 worker，避免读到写入一半的 JSON。容器可创建被忽略的 `backups/` 目录，执行 `docker compose cp agent:/data/qq-config.json ./backups/qq-config.local.json`，编辑私有副本，再用 `docker compose cp ./backups/qq-config.local.json agent:/data/qq-config.json` 放回，最后 `docker compose start agent`。副本不要加入 Git；改白名单无需删除数据库或重置扫描时间。

## 实现边界与可选设置

| 边界 | 当前行为 |
|---|---|
| 输入 | 每事件五附件、每文件 10 MB、PDF 20 页、邮件 25 MB |
| 工作上下文 | 最近最多 20 个完整问答，32,000 字符；关键状态保留，否则停止处理 |
| 模型调用 | 每事件四次 HTTP 请求，提取、工具、重试和回复共用；默认不限累计用量 |
| 图像输入 | 最多六张图/页面；未读内容不能当作已核对 |
| ZIP 邮件 | 超过 18 MB 时保存在本机，邮件说明未附 ZIP |

`watch --request-cap N` 可选设置累计额度。上述实现边界不是 `.env` 可调项，修改前请看[架构](architecture.zh-CN.md)。

`VISA_MS_CLIENT_ID`、`VISA_MS_TENANT`、`VISA_OUTLOOK_MAILBOX`、`VISA_OUTLOOK_ALLOW_SENDERS` 属于另一个 Graph 试接适配器；QQ 不需要填写。Graph 尚未验证真实 OAuth，WhatsApp 当前只有接入设计与会话模拟。

[Docker secrets](docker.zh-CN.md#可选-secrets) 的覆盖配置会清空字面密钥。Windows 交互配置使用 DPAPI 保存 QQ 授权码，加密文件不能迁往 Linux；无交互配置不把授权码写进 JSON。
