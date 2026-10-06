# QQ 邮箱真实接入

QQ 使用 Python 标准库 `imaplib`、`email`、`smtplib`，无需 Azure 应用。Windows 授权码通过 DPAPI 加密存到 `data/qq-test/qq-auth.bin`，不写入仓库、模型提示词或日志。

## 启动与停止

在 QQ 邮箱网页“设置 → 账号与安全 → 安全设置”开启 IMAP/SMTP、生成授权码。[QQ 官方步骤](https://help.mail.qq.com/detail/106/985)

```powershell
uv run python scripts/configure_qq.py
uv run python -m visa_agent.qq_mail probe
uv run python -m visa_agent.qq_mail watch --hitl off --send-replies
```

配置时，允许的发件邮箱留空表示开放收件；填一个地址则仅接收该测试邮箱。授权码在终端隐藏输入。`probe` 只检查 IMAP/SMTP 登录，不发邮件。

## 样例调试开关

Windows 直接双击 [sample-debug-on.cmd](../scripts/sample-debug-on.cmd) 开启，双击 [sample-debug-off.cmd](../scripts/sample-debug-off.cmd) 恢复正常材料检查；也可以执行：

```powershell
uv run python -m visa_agent.qq_mail samples --allow-samples on
uv run python -m visa_agent.qq_mail samples --allow-samples off
```

配置写入本地 `qq-config.json`，当前版本 worker 每轮读取，无需重启或前端。默认关闭。**作用于下一轮轮询创建的新邮件案件和 `/reset` 后的新案件**；已有案件保留创建时模式，回复、日志、ZIP 标注其演示属性。切换后用新邮件线程测试，或先在旧线程仅发送 `/reset`，等回复后再发附件。

开启只允许明确标记的 sample 参与材料检查；信息缺项、冲突、模糊/损坏、来源无法定位仍不能通过。普通垃圾文件不会因为开关而自动变成有效材料。它与 HITL 开关独立，客户邮件内容不能改本机配置。材料真伪鉴定不在本服务范围。

完整 Visitor 样例可用 `datasets/intake/visitor-example-TEST-ONLY.xlsx` 加 `datasets/formatted-materials-v2/visitor/` 中的 `identity.jpg`、`funds-scan.pdf`、`work.jpg`。四个附件一起发，正文说明要去英国旅游。本机已把这四个文件放到 `external-materials/sample-debug/visitor/`，便于全选附加。开关实测见 [sample-switch.md](sample-switch.md)。

本次按用户要求启用**开放收件、任意主题、关闭 HITL、自动回信**。每个新邮件线程建一个案件，同线程回复继续处理。当前进程每 15 秒轮询一次；关机后需要重新启动命令。首轮真实验证用了 12 次模型请求，随后将累计上限调至 24 次供用户亲测，计数跨重启保留；SOUL 更新复验又用了 4 次，当时累计 16/24。最新用量见本机 `qq-watch-last.json`。需要更多测试时由操作者明确修改 `--request-cap`，历史使用量不清零。

```powershell
# 查看最新扫描、最近回信、模型与规则记录
Get-Content data/qq-test/qq-watch-last.json
Get-ChildItem data/qq-test/qq-previews
uv run visa-agent --data data/qq-test inspect <case_id>
uv run visa-agent --data data/qq-test trace <case_id>
# 停止后台收件：当前事件处理完后退出
uv run python -m visa_agent.qq_mail stop
```

也可单次运行 `poll`；不带 `--send-replies` 时仅保存预览，带此参数时发送有效的待发回复。后台 worker 运行期间优先查看日志，避免人为重复启动扫描进程。

## 自己测试

客户直接发邮件、回复邮件和发送附件即可，整个流程在邮箱里完成，不需要打开项目页面。页面和 CLI 是开发者查看日志的辅助入口。

2026-10-07 更新：回复跟随本轮中文/英文，路线明确后附双语 XLSX 信息表，支持回传、缺项检查及完成后的 ZIP 附件。见 [信息收集 SOP 与测试](application-information.md)。累计请求默认不限；`--request-cap` 仅在操作者显式设置时启用。

1. 用另一个邮箱向配置的 Agent 邮箱发一封新邮件，主题任意。正文可写“我在中国，30岁，想去英国旅游，不知道需要什么材料”。预期自动建案，中文回复询问信息并显示材料进度。
2. **直接回复 Agent 的邮件**，提供姓名、时间、资金来源等信息。预期沿用同一案件，保留先前事实。
3. 将 PDF、PNG 或 JPEG 作为附件上传。普通案件不能把标注为样例的文件当正式材料；乱码、缺页和冲突应阻止完成。正文内嵌图片及签名图片不作为材料，请用“添加附件”。
4. 换另一个发件邮箱或发起全新邮件线程，预期创建新案件；引用其他发件人的案件线程会被拒绝。
5. 正文仅写 `/exit`、`/start`、`/reset` 或 `/status`，去掉签名。命令不调用模型；`/reset` 新建空白案件，保留旧案以便追溯。

正常检查模式不会把合成样例当正式材料；开启上述样例调试后，新案件可用配套样例走到演示完成。自动完成只代表本版材料检查满足，报告标记“未经人工审核”；它不鉴定真伪，也不承诺签证结果。人工开关和五种案件状态见 [hitl-outlook.md](hitl-outlook.md)。

## 实现与失败处理

| 入口 | 作用 |
|---|---|
| `QQConnection` | 固定连接 `imap.qq.com:993`、`smtp.qq.com:465`，校验证书；只读收件箱，不删信、不改已读状态 |
| `QQInbox.poll` | 通过 UIDVALIDITY/UID 保存扫描位置；默认从配置时间后的邮件开始，单次最多扫描 100 条，处理上限默认 5 条 |
| `parse_mail` | MIME 解码、From/To/Reply-To 校验、正文与附件拆分、常见历史引用过滤；不加载远程图片 |
| `QQInbox.receive` | Message-ID 去重，References/In-Reply-To 绑定线程，交给现有 `Inbox` 和 `VisaService` |
| `send_prepared_reply` | 与 Outlook 共用发送前版本检查、事务占位和发送结果记录 |

整封邮件限 25 MB，最多五个附件；每文件仍限 10 MB、PDF 20 页。畸形 MIME、附加 `.eml`、不支持的格式、冲突的身份头明确拒绝。自动回复、邮件列表、`Precedence: bulk/list/junk`、自己的发信及已识别的 QQ 系统通知发件人会过滤。这些规则不是完整的垃圾邮件分类器，也没有对互联网 From 地址做客户实名认证。

发送记录状态包括 `prepared`（等待发送）、`sent`（SMTP 接受）、`superseded`（案件已变更）、`uncertain`（连接中断，是否送达未知）、`ignored`（系统通知）。旧版 `failed` 记录继续保留。现在模型检查失败时，也发送应用生成的失败说明；`result.error`、失败事件与 `BLOCKED` 状态保留，回信不会夹带内部异常。`sent` 只表示邮件被接受，不等于案件完成或客户已读；不确定发送不会自动重发。文件、模型失败及被拒邮件记录保留在本机。

后台网络错误最多连续重试两次，第三次失败停止并留下错误类型；不会伪造成功。没有新邮件时不调用模型。显式配置累计额度时，达到额度暂停；未扫描的邮件仍在服务器。读取或模型失败的案件需要操作者查看记录、处理原因后重试，不承诺无人值守生产运行。

## 当前收集体验

当前邮件仍以 HITL 关闭运行。清单满足后直接通知“材料收集完成”，不等待人工或额外模型交付决定；原文件与报告保留本机。每轮采用简短的收到、收齐、待补充和进度结构，配少量 emoji。详见 [workflow 与稳定性设计](collection-workflow.md) 及 [本轮验收](validation/collection-ux.json)。以下 SOUL 首轮数据保留为历史记录。

## SOUL 与顾问语气

[SOUL.md](../src/visa_agent/prompts/SOUL.md) 定义助手身份、热情耐心的沟通原则、邮件内继续办理，以及不得改变材料检查结果的边界。`persona.py` 加载文件，提取和引导两阶段都把它放在系统指令最前面；其长度计入工作上下文预算，运行记录保存 `soul_sha256`。文件随 wheel 一起安装，修改后重启 worker 生效。

模型选择下一步问题、解释主题和沟通方式；`conversation.py` 负责实际欢迎、承接、补件理由、进度与准确的结论措辞。因而修改纯问候语应同时看这个文件；只编辑 SOUL 不会任意改写所有固定句子。首次欢迎、继续回复时致谢，等待补件时鼓励先提供已有材料；客户回信中不显示 HITL 或开发工具操作。

新版复验曾将“住在中国”推断为英国境外申请，原始 `BLOCKED` 结果保留。首次自述的申请地点现在必须明确陈述，否则留作待确认并继续询问，不能从居住地推断；新旧回复和用量见 [SOUL 验收记录](validation/qq-soul.json)。

本次更新的全量离线测试 **170 项通过**；两封真实初次咨询共 **4 次模型请求，11,760 输入 / 1,066 输出 token**。最终复验自动创建新案件，中文欢迎、三个问题和材料进度通过邮件送达 Outlook，案件保持 `WAIT_USER`。打包检查确认 SOUL 随 wheel 分发。中英文“模型检查失败仍发说明、保留失败状态、不重复发送”使用模拟模型故障验证，没有刻意制造真实服务故障。

复用边界：PydanticAI 管模型结构化调用，Python 标准库处理 IMAP、SMTP 和 MIME，SQLite 保存事务与唯一约束。案件路由、规则与发送记录是本项目的业务代码。Camunda、DocProof、LangChain 仅参考流程设计，当前没有部署 Chatwoot，也没有接入一套现成的端到端签证服务。

## 本次实测边界

- 真实 QQ IMAP 与 SMTP 登录已通过，授权码已在本机加密保存。
- 真实服务器返回单数字日期 `6-Oct`，标准解析器不能直接读取；已修复并加入回归测试。
- 开放收件首次把 QQ 系统推广邮件误建案，消耗两次真实模型请求。预览未发送，随后标记忽略；原失败案件及用量保留，新增系统通知过滤。
- Outlook 实际中文咨询已自动建案、中文回信，且在客户收件箱确认收到。同线程 PDF 补件沿用原案件；样例护照被识别为 `sample`，未生成材料包。
- 实际补件发现中文完整日期被错误拒绝、模型选其他问题时漏报样例说明；增加完整中文日期的来源核对与独立样例说明。没有年份的日期仍不能默认为某年。
- 提示词修复后模型仍对无年份日期补年份，来源校验拦截后案件停在 `BLOCKED`，该次失败保留。现在首次自述的申请/旅行月日保留为待确认，日志明确记录缺年份；文件日期和修改已有日期继续严格校验。
- Outlook 的纯文本回复分隔线曾让 `/reset` 失效并多耗两次请求。已清理引用分隔线；再次通过真实邮件发送 `/reset`，零模型请求创建空白案件，旧案件和失败记录保留。
- 接口离线测试覆盖重复投递、UIDVALIDITY 变化、线程劫持、断线后的发送歧义、旧回复失效、MIME/附件和 30 次连续邮件恢复。实际客户收发结果单独记入 [validation/qq-mail.json](validation/qq-mail.json)。

首轮全量离线 **166 项通过**（71.69 秒）。该轮真实邮箱实验 **12 次模型请求，38,333 输入 / 3,675 输出 token**；价格未配置。共发送七封客户回复，含重置命令、失败复现和修复复验，不能当作七个成功签证案件。该轮最终复验九项断言均满足：继续重置后的案件、中文完整日期保存、无年份日期不猜测、样例分类及说明、保持 `WAIT_USER`、不交付材料包、SMTP 接受；另在 Outlook 页面确认实际收到。

本机每轮原话、模型输出与原始失败见 `output/qq-mail/review/index.html`，原始事件和发送记录在 `data/qq-test/`。本次只证明已测邮件和补件路径；尚未通过真实邮箱完成整套正式材料交付。

参考 Python 官方的 [IMAP](https://docs.python.org/3.12/library/imaplib.html)、[MIME](https://docs.python.org/3.12/library/email.message.html)、[SMTP](https://docs.python.org/3.12/library/smtplib.html)接口。源码：[qq_mail.py](../src/visa_agent/qq_mail.py)、[mime_mail.py](../src/visa_agent/mime_mail.py)、[mail_outbox.py](../src/visa_agent/mail_outbox.py)。
