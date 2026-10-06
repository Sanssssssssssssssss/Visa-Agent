# 三条路线的最终交付验收

后续发现并修复了普通案件把自填文字清单当证明的缺陷，见[材料接受条件复测](document-quality.md)。本页三路线使用合成字段 PDF，只证明邮件与 ZIP 交付，不能据此认定文档审核可靠。下列记录保留当时实际结果。

**三条路线各 3 轮真实邮件均走到最终 ZIP 交付。** Outlook 发件，经 QQ 收件、真实模型处理后由 QQ 回复；最后从 Outlook 实际下载 ZIP，与发送件逐字节相同。HITL 关闭，客户文本使用普通中英文，材料为明确标注的合成样例。

| 路线 | 三轮状态 | 邮箱下载件 | ZIP 内文件数 | 原始 PDF 页数 |
|---|---|---|---:|---:|
| Visitor | WAIT_USER → WAIT_USER → COMPLETE | [材料包](../examples/packs/visitor-demo.zip) | 10 | 3 |
| Student | WAIT_USER → WAIT_USER → COMPLETE | [材料包](../examples/packs/student-demo.zip) | 11 | 4 |
| Skilled Worker | WAIT_USER → WAIT_USER → COMPLETE | [材料包](../examples/packs/skilled_worker-demo.zip) | 11 | 4 |

每案第一轮咨询，第二轮交信息表和护照，第三轮交剩余证明。缺件时均未完成；每案保持同一个邮箱会话和案件。三个初始信息表也从 Outlook 下载，与发出字节一致。ZIP 校验覆盖 CRC、原始附件哈希、XLSX 可打开、PDF 可读取、HTML 内部链接及最终邮件正文。

本轮全套离线 **202 passed**；发现重复催填已完成表格后，修复并通过 **28 项相关测试**，随后三条路线再次用真实 API 分批回放，均完成，第二轮均不再索要填表。两个真实 API 反例（普通案件提交样例、表格指令注入并附全部材料）均停在 WAIT_USER。Ruff 通过。

实际邮箱 15 次请求，修复后回放 15 次，反例 8 次；合计 **38 次、187,299 input / 12,482 output tokens**，模型为 `deepseek-flash`。未配置价格，不估算费用。没有用模拟响应替换服务失败。邮箱原始第二轮重复填表文案保留在[逐轮邮件](full-delivery-transcripts.md)，修复后结果及哈希见[验收数据](validation/full-delivery.json)。

复跑应用和 ZIP 闭环（真实 API，会产生用量；邮箱传输需另行配置）：

```powershell
uv run python scripts/full_delivery_acceptance.py --output output/my-full-delivery
uv run pytest tests/test_delivery_handover.py -q
```

每次使用新输出目录。回放使用冻结合成材料及其相对日期；真实邮箱本次信息表计划申请日期为 2026-10-20。

## 材料包怎么用

解压后打开 `START-HERE.html`。`documents/` 保留提交文件的原始字节，文件名可读；`application-information.xlsx` 汇总填表信息；历史回传表在 `information/source-forms/`；`submission-guide.txt` 是双语申请和预约步骤。检查报告、来源清单、交付记录用于追溯。

ZIP 是整理和传输材料的容器。客户仍须填写官方在线申请，按官方清单上传所需的单个文件，不能把准备表或内部报告当作官方证明。

## 官网核对（2026-10-07）

| 路线 | 当前程序核对 | 尚不能据此认定的事项 |
|---|---|---|
| Standard Visitor | 身份及有效期、行程与离境安排信息、预算和资金、在职自费分支、翻译及跨材料冲突 | 访问目的可信度、资金来源和总体充分性；没有统一最低银行余额。工作证明是本版在职分支的支持材料，不能说所有访客都必须交。 |
| Student | CAS 信息、学费与生活费、适用资金证明的 28 天/31 天条件、英语确认、TB/ATAS 条件和近期资助同意 | CAS/学校登记真实性、课程及所有豁免的资格判断、认可银行和 TB 诊所核验。中国申请人的差别化材料安排不豁免资金条件。 |
| Skilled Worker | CoS 编号、岗位、薪资、雇主及担保编号、英语信息、雇主维护费担保或个人资金、TB/ATAS | 目前只覆盖职业 2134 的材料准备。未实现按工时计算的完整薪资资格、担保登记核验及英语证据资质认证；其他职业不能自动完成。 |

依据：[Visitor 资格](https://www.gov.uk/standard-visitor)、[Visitor 材料指南](https://www.gov.uk/government/publications/visitor-visa-guide-to-supporting-documents/guide-to-supporting-documents-visiting-the-uk)、[Visitor 资金说明](https://www.gov.uk/government/publications/visit-guidance/visit-caseworker-guidance-accessible--2)；[Student 材料](https://www.gov.uk/student-visa/documents-you-must-provide)、[资金](https://www.gov.uk/student-visa/money)；[Skilled Worker 材料](https://www.gov.uk/skilled-worker-visa/documents-you-must-provide)、[岗位与薪资](https://www.gov.uk/skilled-worker-visa/your-job)、[英语](https://www.gov.uk/skilled-worker-visa/knowledge-of-english)。

三条基础清单与上述材料指南对应，但“本版收集完成”不能表示已经满足英国全部签证要求。模拟银行、学校、雇主材料也不能证明真实资格。本次使用明确标注的虚构材料，只对三个指定测试案件在本机开启演示模式；普通邮件不能开启该模式。

## 最后的申请与预约指引

邮件和 ZIP 都给出对应路线的官方入口：[Visitor](https://www.gov.uk/standard-visitor/apply-standard-visitor-visa)、[Student](https://www.gov.uk/student-visa/apply-online)、[Skilled Worker](https://www.gov.uk/skilled-worker-visa/apply-from-outside-the-uk)。客户填写申请、按账户支付适用费用并保存回执，再按账户指引核验身份。Student/Worker 可能使用 ID Check App；指定到签证中心时再选择可用 slot。预约须在申请之后进行，地点通过 [GOV.UK 签证中心目录](https://www.gov.uk/find-a-visa-application-centre) 查找。程序未代填提交、付费或预约。

## 表达与实现

`prompts/SOUL.md` 改为简短客服口吻。测试来信使用自然语言，不带内部字段名或期望状态。模型抽取事实并选择优先事项；来源校验、完成状态和邮件附件由代码控制。抽取阶段仍保留必要的字段和引用约定。完成邮件及官方入口来自可检查的中英文本，不能让模型随意宣布已提交或编造预约链接。
