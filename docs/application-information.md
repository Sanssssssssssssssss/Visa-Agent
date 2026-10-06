# 双语申请信息收集

QQ 邮件流程现在同时收集**文件和填表信息**。回复跟随本轮客户正文使用中文或英文，明确的语言要求优先；只有附件时沿用上轮语言。姓名、国籍和附件语言不决定回复语言。信息表统一中英双语。

先确认旅游、学习或工作，再发送该路线的 `application-information.xlsx`。客户填写 `Information` 页 **C 列**，保存后回复邮件并附上文件；`Documents` 页列材料和官方来源。暂时没有答案可以留空，回传空白不会删除此前答案。不要修改隐藏字段或加入公式。

回复用 `🟩⬜` 分别显示文件和信息进度。HITL 关闭时，两类检查都满足才完成；QQ 自动附上不超过 18 MB 的 ZIP，超限则明确告知尚未发送。生日、护照号或 CAS 的自填信息不能代替正式文件证据。

## SOP 核对

核对日期：2026-10-07。规则版本包含 `rules.py`、`intake.py`、`intake_schema.py` 的内容哈希。

| 路线 | 新增的信息准备 | 官方依据 |
|---|---|---|
| Visitor | 住宿、住址及居住时间、父母信息、收入、违法记录；按情况收集旅行史、雇主、伴侣、资助人和英国亲属信息 | [GOV.UK 申请指南](https://www.gov.uk/standard-visitor/apply-standard-visitor-visa)。父母信息不详可解释；收入可为零，不要求先付款预订 |
| Student | CAS、学校、课程和日期、过去 12 个月官方资助情况；适用时要求资助机构书面同意 | [GOV.UK 材料指南](https://www.gov.uk/student-visa/documents-you-must-provide)。护照及 CAS；资金、TB、ATAS、资助同意按条件判断 |
| Skilled Worker | CoS、岗位、薪资、职业代码、担保执照、工作日期和地点、雇主是否要求 ATAS | [GOV.UK 材料指南](https://www.gov.uk/skilled-worker-visa/documents-you-must-provide)。部分岗位要求无犯罪证明；自动分支仍仅覆盖 2134 |

生日、出生地、联系方式、曾用名等共同字段属于本项目的信息准备清单。公开指南没有列出全部动态在线问题，因此这里不声称覆盖 UKVI 全部正式问题，也不把每个准备字段称为通用法定要求。成年境外主申请人、资金和职业等原有限定仍适用，未覆盖分支阻止完成。

表格是准备表，未替客户提交申请。[UKVI 语言选择页](https://visas-immigration.service.gov.uk/alt-language-selection-skip-visa)允许切换问题语言，但正式在线答案须使用英文。客户可以先用中文提供信息；本版不提供认证翻译。

## 实现与调试

`intake_schema.py` 定义有限字段、双语标签、格式、适用条件和来源。`intake.py` 用 openpyxl 读写真实 XLSX，限制 ZIP 展开大小、行列数，拒绝公式、宏、外链、错案件/路线/版本以及重复或缺失的字段 ID。

自填事实标记为 `intake`，引用包含 `Information!C行号` 和原文；日期、金额、邮箱、布尔值分别校验，“不知道”不等于“否”。由明确生日推导年龄的依据进入日志。模型不能将表格重新标记为护照或资金证明。

改填只取代原信息表答案；与消息或证件的冲突仍保留双方来源。`info:*` 表示缺项，`form:*` 表示表格或字段错误；文件要求仍独立检查。追溯顺序：**原文/单元格 → Fact → Check → 状态 → 客户回复**。完成包包含整理好的双语信息表、原始文件、清单与来源。

QQ 启用 `application_forms=True`。旧 15 案冻结回放、CLI/页面保留原文件收集范围；直接调用新流程用 `VisaService(..., application_forms=True)`。旧邮箱案件收到新消息后升级并重新检查，旧完成记录失效。旧版通过不能证明新版信息完整。

## 体验和验收

[空白表、已填例和 bad cases](../datasets/intake/README.md) 都在仓库。示例明确使用虚构信息，普通邮箱案件不能用合成文件完成正式材料收集。

```powershell
uv run pytest -q tests/test_intake.py
uv run python scripts/intake_acceptance.py --output output/intake/my-live-run
uv run python -m visa_agent.qq_mail watch --hitl off --send-replies
```

真实 API 场景包含三路线完成、生日和邮箱补正、公式、护照号冲突、提示注入、普通案件中的样例文件、中文→英文→中文切换。每事件重复投递不增加请求，轮间重开 SQLite。新实验用新输出目录，失败记录保留。

按用户要求取消累计请求上限，仍记录全部用量；保留单事件四次请求、一次瞬时网络重试及无进展停止。结果见 [验收记录](validation/application-information.json)。这些结果不代表高并发、真伪认证或正式签证申请验收。

2026-10-07 实测：本地全量 **199/199**，100.27 秒；Ruff、原 15 案冻结哈希通过。真实 API 首批 7/10，三个失败均由“旅游 / tourism”误判冲突造成；保留失败后修复，完整复验 **10/10**。引导菜单调整复验 3/3；最后加入“文件齐全但信息表含强行完成指令”的检查，复验 2/2。每批源码哈希与输入哈希均在报告中。

真实 Outlook → QQ → Outlook 两封回信均在客户收件箱核实：首封英文并附双语 XLSX；同线程回传表格后改用中文，指出邮箱错误与缺生日，仍为 `WAIT_USER`。这没有验证真实客户整套材料的签证适用性。新版开发、失败复现和复验合计 **109 次请求，504,747 输入 / 29,580 输出 token**；未配置价格，不估算费用。
