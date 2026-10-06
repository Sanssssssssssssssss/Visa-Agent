# Model replies and mail recovery / 模型回复与邮件恢复

2026-10-07：修复“模型识别了去玩/读书，程序却拒绝路线并重复提问”的真实邮件问题。最新离线测试 **232 passed**；最终真实模型对话 **9/9 轮**；Visitor、Student、Skilled Worker 的 v2 图片/扫描件回放均走到 `COMPLETE`，ZIP 校验通过。[逐轮回复与用量](validation/conversation-reply.json)。

The intent keyword gate and fixed live reply renderer were the cause. The model now interprets the customer's meaning and writes `Guidance.reply`; the application appends current progress. Exact sources, typed values, evidence requirements and delivery state remain independently checked. These checks do not prove semantic understanding or document authenticity.

## Changes / 改动

- `.env` 自动加载，环境变量优先；`.env.example` 包含模型、HITL、邮箱目录、轮询间隔和初始化收件策略。凭证与真实邮件不进 Git。
- 收件初期的明确改口可更新路线/目的；旧事实不删除，有来源和审计。身份证明、资金和文件冲突不能随之消失。
- 清理 163 引用邮件和默认签名；旧进度页脚不反复塞进模型对话上下文。
- 正常回复与完成交付的说明均由模型撰写。回复模型失败保留已提取事实；工具/提取失败保留失败事件，尝试模型解释，最终服务通知保证有非空回复内容。
- 合法邮件的附件格式、数量、大小问题也会回复。自动回信、系统通知和串案引用仍被拒绝，防止邮件循环和错误收件人。
- 发件失败写入 `mail_attempts`，15 秒起退避至 300 秒，重启继续。QQ 沿用 Message-ID；超时后至少一次投递可能重复。`sent` 仅代表供应商接受，不能保证已到客户收件箱或已读。

## Verification / 验证

| 检查 | 实际结果 |
|---|---|
| 离线 | 232 passed；包含错误工具参数、越案工具读取、模型不可用、异常附件、SMTP 超时后重启重试、去重 |
| 最新真实模型对话 | 9/9；口语路线、明确改口、否定、未决定、第三人计划、提示注入、居住地不等于申请地点；仅一次进度页脚 |
| 图片/扫描 PDF 完整收集 | v2 三路线各 3 轮，全部 `WAIT_USER → WAIT_USER → COMPLETE`，实际 SQLite、OCR、图片输入及 ZIP |
| 实际客户线程修复 | 先备份数据库；只撤销过时的词表拒绝，保留原始事件；模型重新处理原输入并发送纠正回复及信息表，QQ SMTP 接受 |

保留的失败：第一次图片回放误选旧版 v1 材料，Visitor 的雇主联系方式冲突，停在 `BLOCKED`（该批 2/3 完成）。未强行忽略冲突或改写预期；验收脚本默认路径修正为原文档指定的 `formatted-materials-v2` 后重新执行三路线。早期模型回复有重复进度页脚，最终 9 轮未再出现。这些是有限样本结果，不能承诺模型永不犯错。

本轮所有真实调用（含早期回放、失败与纠正邮件）共 **97 次请求，386,100 input tokens，33,120 output tokens**；模型 `deepseek-flash`。未配置价格，未估算费用。异常注入和重试测试使用模拟邮件传输；完整路线新回放为本地交付，不能混同成三次新的真实邮箱投递。

## Replay / 复现

```sh
uv run pytest -q
uv run python scripts/conversation_acceptance.py --output output/my-conversation --repeat 1
uv run python scripts/full_delivery_acceptance.py --formatted --output output/my-delivery
```

真实调用读取本机模型配置并产生费用；输出目录必须是新的。对话回复、状态、用量和失败留在输出目录。生产收件服务使用独立的 `data/qq-test`，这些回放不发送邮件。
