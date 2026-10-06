# Visa Agent

一个可回放、可检查的英国签证材料准备 Agent。支持 Visitor、Student、Skilled Worker 的有限基础分支：接收消息和附件，保存有来源的事实，检查缺项与冲突，等待补件，生成材料包。当前邮箱关闭人工材料包审批：清单满足后自动通知材料收集完成。也保留按案件开启人工复核的部署选项。

最新版本支持 **HITL 开关与 QQ 真实邮件接入**，邮件回复已改为收到、收齐、下一步和进度；验证记录见 [收集体验与稳定性](docs/collection-workflow.md)。客户只需发邮件，系统自动建案并邮件回复；同线程继续原案件，无需使用项目页面。[SOUL.md](src/visa_agent/prompts/SOUL.md) 定义热情、耐心的服务原则，并前置于模型系统指令。见 [QQ 操作与实测](docs/qq-mail.md)、[邮件验收记录](docs/validation/qq-mail.json)、[SOUL 更新验证](docs/validation/qq-soul.json)。Outlook Graph 适配器也已实现，但本机尚无应用 Client ID，未验证 Graph 收发。

此前 HITL 真实模型实验共 25 次请求、5 案中 4 案通过。中文完整输入已自动生成演示材料包；八轮渐进案例漏提取目的，原失败保留。见[开关与工作流](docs/hitl-outlook.md)、[该轮记录](docs/validation/hitl-outlook.json)及[历史验收](docs/acceptance.md)。

最新修复：[自填文字附件曾被误当成证明，已复现并收紧接受条件](docs/document-quality.md)。普通文字页、截图和公开样例的真实 API 反例均等待补件；原来的三路线合成演示只验证交付流程。

完整交付记录：[三条路线各 3 轮真实邮件 → ZIP 下载核对](docs/full-delivery.md)。可查看 [Visitor](examples/packs/visitor-demo.zip)、[Student](examples/packs/student-demo.zip)、[Skilled Worker](examples/packs/skilled_worker-demo.zip) 演示包及[逐轮邮件](docs/full-delivery-transcripts.md)。最终邮件附 GOV.UK 申请和身份核验/预约步骤。这不能证明满足全部英国签证资格要求。

## 安装

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。在仓库根目录执行：

```powershell
uv sync --locked --python 3.12
uv run visa-agent --mode offline verify-dataset
uv run pytest -q
```

依赖安装进项目 `.venv`，版本固定在 `uv.lock`。锁定的 RapidOCR wheel 自带中英文 OCR 模型；运行不要求另装 GPU、Tesseract 或 OCR 服务。第一次安装需要下载依赖，离线测试不访问模型 API。

## 两分钟体验

按 [QQ 接入说明](docs/qq-mail.md) 配置 Agent 邮箱并运行收件进程。客户直接发邮件咨询，在原邮件中回复信息并附文件；系统自动建案、补件和回复，不需要前端。关闭 HITL 时仍必须通过材料及信息检查，才能发送材料 ZIP。

现成反例在 [datasets/document-quality](datasets/document-quality/README.md)，公开银行扫描件的获取方式见[来源说明](docs/public-images.md)。这些文件适合检查能否正确要求补件；不能用于正式申请。三路线合成图片仅用于[演示与 OCR 回放](datasets/formatted-materials-v2/README.md)。

中文分步体验、`/exit`、一键清空、邮箱/WhatsApp 身份隔离及本轮真实结果见 [会话与引导验收](docs/session-guidance.md)。当前保留最近 20 轮，模型在每轮检查后选择最多三个优先问题。普通事件通常消耗两次模型请求。

可以直接用中文或英文提问，例如“第一次办英国签证，怎么申请，需要什么材料？”每轮回复附材料进度。默认 `VISA_VISION=1`：图片传原图，PDF 传渲染页与 OCR；最多 6 张图/20 MB，超过范围需拆分或复核。只有本机操作者明确开启的合成演示案件允许使用测试材料；客户邮件不能开启演示模式。

想看模型每次实际输出及客户收到的回复，使用下方 `trace` 命令，或查阅[实际邮件原文](docs/full-delivery-transcripts.md)。完整文件和运行日志保留在本地。

```powershell
uv run visa-agent --mode offline replay datasets/cases/dev_visitor.json
```

记下输出的 `case_id`、`version` 和 `pack_path`。此时应为 `READY_FOR_REVIEW`。解压 ZIP，打开 `report.html`，检查原件、字段来源及清单，然后独立执行：

```powershell
uv run visa-agent inspect <case_id>
uv run visa-agent review <case_id> --version 3 --decision approve --reviewer your-name --notes "已核对本次合成样例的材料和来源"
uv run visa-agent trace <case_id>
```

将 `<case_id>` 换成实际案件 ID；版本以 `inspect` 输出为准。审批后为 `COMPLETE`。`--approve-demo` 仅用于合成回放中模拟顾问动作，会明确记录 `synthetic-test-adviser`。

默认 `--mode live`。上述显式选择的 `offline` 使用 PydanticAI `FunctionModel` 读取合成材料的字段标签，验证业务逻辑；它不能说明模型对自然语言材料的理解能力。

## 实际调用模型

当前 QQ 流程还收集申请信息：客户收到中英双语 XLSX，填 C 列后回复邮件，系统检查缺项和格式，完成后发送材料 ZIP。回复跟随本轮中文或英文，进度使用 emoji。见 [双语信息收集说明](docs/application-information.md) 和 [可直接打开的测试表](datasets/intake/README.md)。旧冻结 CLI/页面回放保留文件收集 V1 范围。

程序从环境变量取配置，不自动读取 `.env`。参见 [.env.example](.env.example)。已有 `DEEPSEEK_API_KEY` 可以直接使用；也可设置 `VISA_API_KEY`。不要把密钥写进命令历史或 Git。

```powershell
$env:VISA_MODEL = 'deepseek-flash'
$env:VISA_BASE_URL = 'https://api.deepseek.com'
uv run python scripts/check_environment.py
uv run visa-agent --mode live accept --only dev_visitor --output output/my-smoke
uv run visa-agent --mode live accept --output output/my-live
```

`accept` 自动执行合成场景的独立审批动作。六案包含三条正常路线和三个冻结验收场景。每次模型 HTTP 请求都在 `data/live-budget.sqlite3` 预记账，重试也计入。当前默认不设累计上限，保留单事件停止保护。历史冻结脚本显式设置的额度仍属于相应实验条件。独立新实验使用新的 `VISA_DATA_DIR`，保留旧记录。

DeepSeek 当前默认思考模式与强制结构化输出工具不兼容，本项目对 `deepseek*` 模型显式关闭思考模式。其他兼容接口仍须先跑兼容性检查。费用单价未配置时报告 token 用量，金额留空。

## 自己发消息、传材料

```powershell
uv run visa-agent new my-case
uv run visa-agent message my-case "我想去英国旅游，请帮我准备材料。" --event-id msg-1
uv run visa-agent attach my-case datasets/materials/dev_visitor/identity.pdf --event-id file-1
uv run visa-agent inspect my-case
uv run visa-agent trace my-case
uv run visa-agent events my-case
uv run visa-agent read datasets/materials/module/chinese.jpg
uv run visa-agent tick my-case --now 2026-10-08T10:00:00+08:00 --event-id reminder-1
```

真实自然语言输入可能得到未确认字段或转人工，不能套用标签样例的成功率。若只想理解程序，请在全局参数加 `--mode offline`，使用 [场景文件](datasets/cases/dev_visitor.json) 中的消息。

人工入口还支持 `confirm_fact`、`reject_document`、`accept_document`、`request_changes`、`dismiss_event`、`dismiss_extraction`、`refresh`。事实/文件 ID 来自 `inspect`，事件 ID 来自 `events`，用 `--target` 指定。所有操作要求当前 `--version` 与复核说明。规则变化后用 `refresh` 重新检查。`accept_document` 表示顾问已核对低质量读取结果，不能救回完全没有页内容的文件。

失败事件保留在 inbox；同一事件 ID、文本和附件重发可重试。已处理事件重复发送不会再改状态。同 ID 换内容会被拒绝。模型没有批准、删材料或发送外部消息的工具。

## 材料和测试

```powershell
uv run ruff check src tests scripts
uv run pytest -q
uv run visa-agent --mode offline accept --output output/offline
uv run visa-agent --mode offline replay datasets/cases/dev_stale_approval.json --approve-demo
```

[数据集说明](docs/dataset.md)列出 15 个场景、原始 PDF/图片、变体、预期结果和来源。`verify-dataset` 检查冻结哈希；`scripts/generate_dataset.py --force` 仅在明确建立新验收基线时使用，不能用来掩盖一次失败。

材料包包含 `originals/`、`report.html`、`manifest.json`、`review.json`。审批绑定案件版本和清单哈希；提交审批前重新核对 ZIP 清单、文件集合和原件哈希。模型运行记录、客户消息和附件默认只在本地 `data/`，该目录不提交 Git。

## 实现入口与边界

[implementation.md](docs/implementation.md) 从 `handle_event()` 逐步解释状态写入、上下文、工具预算、规则与恢复；[acceptance.md](docs/acceptance.md) 记录实际检查和失败修正。

应用采用直接函数调用：PydanticAI 提取候选事实，Python 检查要求，SQLite 保存状态。客户回复由检查结果生成，最多三个优先问题。CLI、本地上传页面和 QQ 邮件调用同一案件引擎；真实 WhatsApp 尚未接入，后续可由 Chatwoot webhook 转成 `CaseEvent`。

V1 仅覆盖成年、境外、无家属、无拒签解释的一部分情况。Visitor 自动分支采用在职自费场景；Student 自动资金计算限 GBP、自有资金；Skilled Worker 职业自动分支限 2134。其他国籍/居住历史、资助形式、英语证明路径等有转人工边界。SOP 的完整限制见实现说明。

仓库是本地单操作者工具。SQLite 写事务包含模型调用，案件间也会串行；部署多人服务前需增加鉴权、案件隔离、后台任务及按案锁。这里的独立审批是应用权限边界，没有部署级身份认证。

代码 MIT；官方资料和第三方样例的版权归原作者，见 [来源说明](docs/dataset.md)。
