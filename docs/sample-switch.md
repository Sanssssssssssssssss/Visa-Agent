# 邮箱样例调试开关

Windows 双击 [开启样例调试](../scripts/sample-debug-on.cmd) 或 [恢复正常检查](../scripts/sample-debug-off.cmd)。配置保存在本机 `data/qq-test/qq-config.json`，worker 每次轮询重新读取；不需要前端或修改数据库。

| 模式 | 新邮件案件 |
|---|---|
| 样例调试开启 | 允许明确标记的 sample 用于演示，回复和 ZIP 标注测试用途 |
| 样例调试关闭（默认） | sample 不计入正式证明，要求客户补实际材料 |

开关与 HITL 独立。信息缺项、冲突、读不清、来源错误仍阻止完成；不提供真伪鉴定。已有案件保留原模式，切换后发新邮件或先发 `/reset` 再重新交材料。客户来信不能修改此配置。

快速体验：打开本机 `external-materials/sample-debug/visitor/`，全选四个附件发给 Agent 邮箱，正文写“你好，我想去英国旅游，填好的表和材料放附件了”。目录是虚构信息表、两张 JPEG 和一份扫描 PDF，原始来源在 `datasets/intake/` 和 `datasets/formatted-materials-v2/visitor/`。它们适合演示，不能用于申请。

CLI 等价操作：

```powershell
uv run python -m visa_agent.qq_mail samples --allow-samples on
uv run python -m visa_agent.qq_mail samples --allow-samples off
```

代码入口：`qq_mail.main()` 写本机开关并按轮询读取；`QQInbox.receive()` 将该配置交给 `Inbox.receive_connector()`，在建案或重置时设置已有的 `Case.test_mode`。没有增加另一套材料引擎。原来的严格检查和演示标记继续复用。

相关离线测试 **55 passed / 67.49 秒**，覆盖完整交付、缺件不完成、邮件文字不能开调试、切换后旧案保留、`/reset` 使用新模式，以及 worker 无重启读取新配置；Ruff 通过。真实邮件对照结果见[验收数据](validation/sample-switch.json)。

**真实邮箱 2/2 符合预期**：相同四个附件在开启时为 `COMPLETE`，从 Outlook 下载 ZIP 并核对与服务器字节相同，包内演示标记存在；关闭时为 `WAIT_USER`，实际收到补件邮件且无 ZIP。两个案件均关闭 HITL，未手改案件状态。本轮共 **3 次请求、17,528 input / 1,965 output tokens**，模型 `deepseek-flash`，价格未配置。本机测试结束后已恢复 `allow_samples=true`。
