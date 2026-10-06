# 原图、客服回复与坏文件测试

2026-10-06 实测 `deepseek-flash`；官方模型列表与账号 `/models` 返回的名称均为 **DeepSeek-V4.1-Flash**。本轮共 **21 次案件运行、31 轮对话、33 次模型请求**，另有 2 次原生 PDF 兼容性请求失败，共 **35/36 次预算**。用量为 **120,467 输入 / 14,540 输出 tokens**；没有配置费用单价。[机器可读结果](../validation/customer-service.json)

21 次运行中，19 次满足最初的应用检查；人工查看回复后补充了“不重复问已知目的、分批上传确实推进”的检查，17 次同时满足两组检查。4 次有问题的历史运行全部保留：两次漏提取已明确的路线，一次漏提取演示护照，一次把 `own money` 当成未覆盖的资助方式。修复后，完整演示连续两次达到 **0/3 → 1/3 → 3/3，READY_FOR_REVIEW**，两个 ZIP 均验证可读且清单一致。没有自动执行批准，也没有把演示包称为真实客户交付。

离线验证：**77 项通过**，Ruff 通过，原始 15 案冻结数据哈希未变。[执行记录](../validation/pytest-customer-service.txt)

| 输入 | 实际结果 |
|---|---|
| 大学公开脱敏图片 / PDF | 原图或渲染页确实发出；遮挡值保留未知，未确认齐备 |
| 空白图片、损坏 PDF | 提示重新上传，记录读取失败类别，进度不增长 |
| 虚构护照、流水、在职证明 | 普通案件阻止样例作为申请证据；只有显式演示模式允许演练 |
| 文件名伪装成流水的餐饮收据、文件内诱导指令 | 没有完成或批准案件；不能据此证明所有攻击都能防住 |
| 中英文新手、语言切换 | 回答申请步骤/材料，询问未知信息，附材料进度 |
| 已在英国的申请人 | 说明自动流程范围，询问现有签证及到期日，交顾问核对 |
| 中断重投 | 31 次重启后的重复事件检查通过，额外请求为 0 |

PDF 固定走 **可见页面渲染 → 图片 + OCR 文本**；图片文件发送原始字节。原 PDF 保留，日志保存文件哈希、页码、发送方式和用量。每轮最多 6 张图、20 MB 图片数据；未发送的页面会明确阻塞核对。本节历史版本的 12,000 字符上限控制文字上下文（当前版本已改为 32,000 字符、20 轮，见 [会话验收](session-guidance.md)），图片 token 另外计入实际用量。原生 PDF 的第一种嵌套格式返回参数错误，第二种供应商格式返回不支持 PDF；没有改写成兼容成功。[DeepSeek 视觉文档](https://api-docs.deepseek.com/guides/vision/) · [模型名称](https://api-docs.deepseek.com/quick_start/pricing/)

回复采用小型、可检查的实现：模型在同一次请求中提取事实、分类材料和识别咨询意图；应用根据检查结果组织中英文回复。步骤和链接固定来自官方指南，进度由代码计算，模型不能编造百分比或批准结果。借鉴 Intercom 的沟通风格、澄清、来源与转人工指导，没有引入客服平台依赖。[Intercom 指导](https://www.intercom.com/help/en/articles/10210126-provide-fin-ai-agent-with-specific-guidance) · [GOV.UK 申请步骤](https://www.gov.uk/apply-to-come-to-the-uk)

主要代码：`vision.py` 负责视觉输入，`conversation.py` 负责回复及进度，`diagnostics.py` 负责读取、OCR、分页、视觉冲突、来源不符、规则未满足、工具参数及运行错误分类。材料问题详情只在本地调试记录展示。图像中识别出的值与 OCR 对不上时需要复核；当前不能自动认证文件真伪。

本地查看所有原话与材料：

```powershell
uv run python scripts/show_case_replies.py output/customer-service-v1 --output output/customer-service-review
# 打开 output/customer-service-review/index.html；筛选 baseline / after / funding-fix / repeat
```

重放命令（付费、累积预算；已有记录不会重复执行）：

```powershell
uv run python scripts/bad_case_suite.py run --manifest datasets/customer-service/manifest.json --output output/customer-service-v1 --label baseline --count 12
uv run python scripts/summarize_customer_cases.py
```

`bad_case_suite.py` 会因保留的历史失败返回非零，即使修复后的行已通过。冻结的原始答案与后补语义检查分别在 `datasets/customer-service/manifest.json`、`semantic-checks.json`。原始 PDF/图片在本地 `external-materials/`，获取方法见此前公开材料说明。

仍未验证：真实客户全套材料交付、文件真实性、未标记的伪造材料识别，以及大规模并发稳定性。本轮是重复场景与坏输入测试；未做吞吐量压测。进度表示当前材料类别的检查情况，清单会随申请信息变化，不是获签概率。
