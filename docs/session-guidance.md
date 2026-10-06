# 会话、中文引导与验收

2026-10-06：中文流程经第九轮恢复到待复核，通过独立**测试人员审批入口**后生成 ZIP。材料是标记清楚的合成演示，不能算真实客户或专业顾问验收。

## 当前实现

- 模型先提取，代码核对来源并运行规则，再由模型选择最多三个未解决问题、解释主题和引导方式。问题措辞、状态、材料进度及风险说明由代码组织。模型不能批准、修改规则或把已失败检查改成通过。
- 最近 **20 轮完整问答**加结构化案件记录；32,000 字符装配预算。先压短长文件摘录，再裁最旧完整轮次；关键事实和规则超限时转人工。事实按同字段、同值、同可用性分组，冲突值分别保留，原始记录不删除。
- 姓名、日期、金额不交给自由摘要重写。每次请求独立装配上下文，不携带历史工具调用，因此不会裁成悬空的工具调用/返回对。日志记录实际保留轮数；字符预算不等于供应商最终请求 token 上限。
- 首轮及相关提问时说明虚假材料风险：可能拒签、取消许可并影响后续申请。样例只表示输入用途，不据此指控客户造假。本产品不做材料真伪鉴定。

压缩策略参考 [PydanticAI 历史处理](https://pydantic.dev/docs/ai/core-concepts/message-history/) 与 [Anthropic 上下文工程](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)：采用结构化记录、近期完整对话和按预算裁剪；没有另造摘要服务。风险说明依据 [GOV.UK Part Suitability，SUI 9–12](https://www.gov.uk/guidance/immigration-rules/immigration-rules-part-suitability)，核对日期 2026-10-06。

## 亲自体验

```powershell
uv run python -m visa_agent.web --data data/my-trial --port 8765
```

打开 `http://127.0.0.1:8765`，选“中文分步演示”。依次发送这些消息，也可以按模型当轮的问题调整回答顺序：

1. 我第一次申请，想去英国旅游，不知道怎么准备。
2. 我在英国境外，从中国申请。我是中国国籍，今年30岁。
3. 我的护照姓名是 Lin Example。没有随行家属，以前也没有被拒签过。
4. 准备2026-10-20提交申请。我自己付旅行费用，预算3000英镑。
5. 2026-11-01去英国，2026-11-15离开，旅行结束后回公司继续工作。
6. 上传 `datasets/materials/dev_visitor/identity.pdf`，说“这是护照，下一步做什么？”
7. 上传同文件夹的 `funds.pdf`，说“这是银行的资金证明”。
8. 上传 `work.pdf`，说“这是在职证明，请核对材料是不是齐了”。

页面显示每轮回复、进度和原始运行记录。完整输出见本地 `output/session-guidance-v1/`；运行下面的导出命令后，打开 `output/session-guidance-replies/index.html` 可以对照材料、模型 JSON 和逐轮客户回复。

```powershell
uv run python scripts/show_case_replies.py output/session-guidance-v1 --output output/session-guidance-replies
```

普通空白案件可上传 `datasets/customer-service/blank.jpg`、`damaged.pdf`，或把上述合成 PDF 当作自己的材料上传：应保留缺项/不可用原因，不能因此完成。公开原版图片获取方法见 [公开图片](public-images.md)，也是样例用途。

## 清空、关闭和身份隔离

| 操作 / 状态 | 含义 |
|---|---|
| `/reset` 或“一键清空” | 新建空白案件；旧材料和对话不进入新上下文，审计原文仍保留 |
| `/exit` | 关闭当前会话；继续发消息不会调用模型，需 `/start` 开始新案件 |
| `/status`、`/help` | 查看当前进度、命令说明；不调用模型 |
| `WAIT_USER` | 等待补充信息或材料 |
| `NEEDS_HUMAN` | 来源、冲突、范围或运行错误需要人工处理 |
| `READY_FOR_REVIEW` | 自动检查满足，等待当前版本材料包复核 |
| `COMPLETE` | 当前版本和材料清单已通过独立审批入口 |

会话关闭是独立标记，不改变材料业务状态。网页 cookie 隔离浏览器工作区；右侧“模拟渠道”允许本地测试人员切换身份。用邮箱 A / 线程 A 发送，再切邮箱 B / 线程 B，两者的材料和历史应分开；切回 A 应恢复。换发件人访问已有线程会被拒绝。

后端绑定 `channel + account + thread + sender`，同时按渠道账户的消息 ID 去重。相同 ID、不同内容会拒绝。邮箱格式、E.164 电话格式验证不等于身份认证；内部 HMAC 接口也不能替代供应商 webhook 验签。目前没有连接真实邮箱或 WhatsApp。

## 实际验收记录

- 真实模型：`deepseek-flash`，59/60 次请求，输入 234,455、输出 12,323 tokens。未配置单价，不估算费用。PDF 实际转页图并与 OCR 一起输入。
- 共六个场景，包含重试和一次继续处理的八条运行记录、29 轮真实客户输入。原始八轮中文测试先后三次未完成，全部保留；四个负面场景符合预期；一条中文案件在第九轮继续处理中完成。
- 首次失败发现中文自费表达过窄、客户自述姓名落在护照字段。修复后，自述姓名别名仍不充当护照文件证据。同一份八轮真实模型输出的离线回放已进入待复核；最终修复后未重跑全新八轮真实模型案例。
- 中文恢复案例由测试脚本通过独立入口确认，ZIP 文件清单、原始附件哈希及审批绑定检查通过。没有执行真实专业顾问核验。
- 空白图片、普通案件提交样例、材料内批准指令均不能完成；英国境内转换申请停在人工处理。来源提取失败现在跨轮保留，需有记录的人工处置。
- 离线测试还覆盖四个身份交错发送、30 个逻辑日、每条重复投递及重建服务恢复；该场景重复三次，共 360 条新输入和 360 次重投。此测试不能证明连续运行 30 天，也不代表生产吞吐。
- 当前 Windows 离线结果：103 passed，61.39 秒；Ruff 通过。

可提交的精简结果在 [validation/session-guidance.json](validation/session-guidance.json)；实际客户回复、原始模型响应及失败原因保存在本地输出中。

```powershell
uv run pytest -q
uv run ruff check src tests scripts
# 会产生真实费用；同一批预算持久化，原始冻结答案不会改写
uv run python scripts/session_acceptance.py run --label manual --only chinese-email --output output/my-acceptance
```

本批已接近请求上限；新验收应另设明确预算和输出目录，不要删预算数据库来继续。核心函数及写入位置见 [implementation.md](implementation.md)。SQLite 当前在模型调用期间持有写事务，多个案件写入串行，适用本机 MVP。
