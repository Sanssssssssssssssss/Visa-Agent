# Behavioral regression / 行为回归

本轮新增 5 项离线回归，完整套件 **237 passed**。真实 API 回放 **29/29 轮通过已声明的行为检查**，状态层意外完成 **0/29**。两轮重复回放后补入清空对话的中英文问答；两个 prompt 版本分别保留指纹和结果。[机器记录及清空问答原文](validation/behavior-regression.json)。

`conversation_acceptance.py` 复用现有 Case 和 trace，按顺序比较：**context → proposal → accepted_facts → checks → state → reply**。`first_divergence` 指出已声明字段最早在哪一步不符；回答不逐字比较。运行材料及源码/锁文件哈希保存在 `experiment.json`，`harness_sha256` 标识该次运行的代码和依赖基线。

| 回归 | 验证什么 |
|---|---|
| 注入错误路线 | 同一口语输入被模型提成 Student，定位到 `proposal` |
| 注入不存在的原文引用 | 路线候选正确但写入被拒，定位到 `accepted_facts`，失败状态跨存储重载可查 |
| 三次要求直接交付 | 没有新证据，护照仍未知，不产生 `COMPLETE`、批准或 ZIP |
| 询问与执行重置 | 询问保留原案件；实际发送 `/reset` 后新建空案，旧记录保留 |
| 真实模型 | 口语、改口、否定、第三人计划、信息不足、提示注入、居住地与申请地点，以及中英清空问答 |

`SOUL.md` 已加入 `/reset`、`/exit`、`/start` 的解释。模型回答客户如何操作；系统执行结果决定是否已经重置。后台已加载新提示词。

本轮真实模型共 **62 requests / 191,851 input tokens / 15,171 output tokens**，未配置价格。这是本地模型回放，未通过邮箱发送这些测试回复。实际邮箱服务继续使用独立数据目录。

`unexpected_complete` 衡量状态与文件交付，不是任意自然语言回复正确率。故障注入中，即使模型说“已齐全”，状态和 ZIP 仍不完成；正文语义仍可能出错。这里验证有限案例，不声称完全控制模型或鉴定材料真伪。

```sh
uv run pytest tests/test_behavior_regression.py -q
uv run python scripts/conversation_acceptance.py --output output/my-behavior --repeat 2
```

真实回放使用新的输出目录，并产生模型费用。查看 `summary.json` 中的 `behavior.expected`、`behavior.observed` 和 `first_divergence`，再用同目录 SQLite 的 run trace 检查原始上下文、模型响应和工具记录。
