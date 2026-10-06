# 文字附件误通过：复现与修复

**确实存在缺陷。** 在普通案件（`test_mode=false`、HITL 关闭）中，三份自写字段 PDF 被当作护照、银行证明、在职证明，错误到达 `COMPLETE`。先前三路线合成演示证明了邮件交付，但没有证明材料接受条件可靠。误通过记录保留在[本轮结果](validation/document-quality.json)的 `baseline`。

修复后，五个真实 API 反例均为 `WAIT_USER`，没有生成完成 ZIP；通过真实 Outlook → QQ → 模型 → QQ → Outlook 的普通案件也收到补件回复，材料 **0/3**、信息 **36/36**，无附件。没有开启演示或人工审批来掩盖这个结果。

| 输入 | 最终真实 API 结果 |
|---|---|
| 自写内部字段 PDF | 自述，不能代替三类证明 |
| 自述护照信息段落 | 自述，护照仍缺 |
| 自写字段的 JPEG 截图 | OCR 可读，但不是护照证明 |
| 普通英文 Passport / Name / Number 页面 | 模型识别为自述，护照仍缺 |
| 大学公开的中国银行脱敏扫描样例 | 样例且 OCR 低置信度，不计入客户证明 |

实际邮件原句：

> plain-language.pdf, bank.pdf, employment.pdf 目前只能作为信息整理，不能替代对应证明。请提供护照原页、银行出具的文件或学校/雇主原始材料的清晰副本。

现在由 `documents.content_role_for()` 限制内部字段清单，模型分类普通文档；`Evidence.admissible()` 不再接受 `uncertain`。旧持久化字段清单同样受限制。规则指纹覆盖材料接受逻辑，规则变化后不能发送旧规则下准备的回复。正常文字 PDF 银行信和雇主信仍可处理；转成图片不会自动获得证明资格。

回归全套 **210 passed / 112.79 秒**；之后新增旧规则邮件测试 **1 passed**，最后收紧工作状态的完整词匹配后，材料与邮箱相关 **40 passed / 14.60 秒**，Ruff 通过。中间一轮曾因模型选择无效问题 ID 失败，后续返回具体允许 ID 后修复，失败保留。合成扫描件三路线初跑仅 Student 完成；Visitor 的测试联系方式冲突、工作状态大小写及 Worker 的英语布尔推断被拦住。修正输入联系方式、规范大小写并明确抽取约定后，重跑 Visitor/Worker 均完成。不能把这些尝试合并宣称“一次全部通过”。

本次缺陷调查含失败重试和图片回放共 **60 次请求，310,320 input / 26,681 output tokens**，`deepseek-flash`，未配置价格。另计此前完整交付的 38 次，本次连续工作累计 **98 次，497,619 input / 39,163 output tokens**。详细用量、每轮回复、源码哈希见[验收 JSON](validation/document-quality.json)。

材料入口：

- [故意自写的反例 PDF/JPEG 和信息表](../datasets/document-quality/README.md)：发新邮件并附表和三份材料，应要求补件。
- [公开银行原页扫描](public-images.md)：本地 `external-materials/public-images/`，有来源和遮盖信息；不是客户本人的有效证明。
- [合成版式与扫描件](../datasets/formatted-materials-v2/README.md)：仅测试 OCR 与演示交付，仍是假数据，不是真实护照或真实银行材料。

```powershell
uv run pytest -q
uv run python scripts/document_quality_acceptance.py --output output/my-quality --only typed-fields self-written-passport screenshot-of-notes ordinary-labels
uv run python scripts/full_delivery_acceptance.py --output output/my-images --formatted --materials datasets/formatted-materials-v2
```

默认完整反例还需要按公开来源说明下载银行样例。每次使用新的输出目录，真实 API 会产生用量。结果只是当前输入覆盖：普通标签材料仍有模型误分类风险；没有实现真伪鉴定，也没有用一套真实申请人的文件证明全部英国签证要求可自动审核。完整申请包应被理解为材料收集交付。

本地 52616 报告预览服务已停止，README 改为邮箱入口；本轮没有部署新的前端。收件进程已恢复，HITL 关闭，普通来信自动建案。
