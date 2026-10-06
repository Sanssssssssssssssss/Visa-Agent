# 公开材料手动测试

2026-10-06 下载、修复并测试。原有 6/6 真实模型验收使用自制合成材料，不能证明能处理这些公开文件。后续已用本页材料完成 12 轮真实处理、23 次请求；结果及失败记录见[压力测试](history/public-stress.md)。

本地可拖入的文件在 `external-materials/try-these/`。在网页右侧选择「空白案件」，每份文件单独开一个案件测试。它们来自不同的公开样例，不属于同一申请人；姓名、账号有遮盖或占位符，日期较旧，预期应保留未知并补问，不能直接交付。

启动时也可使用 `uv run python -m visa_agent.web --sample blank`，避免载入合成申请人背景。

| 文件 | 来源和处理 | 实际读取结果 |
|---|---|---|
| `01-Lloyds-statement-redacted.pdf` | [Bournemouth 大学指南](https://www.bournemouth.ac.uk/sites/default/files/asset/document/TIER-4-GENERAL-BANK-STATEMENT-CHECKLIST-v11JUN2018-2.pdf)第 2–4 页，保留原有脱敏和说明标记 | 3 页整页 OCR，能读取流水正文；低置信度仍阻止自动采用；重复调用存在最低余额字段遗漏 |
| `02-BOC-deposit-redacted.pdf` | [Sussex 大学存款证明样例](https://student.sussex.ac.uk/international/documents/certificate-deposit-example.pdf)第 1 页 | 已修复图片正文漏读，能读取银行、金额、存入日；日期语义在真实试跑中发现并修正；倾斜 JPEG 仍漏读金额 |
| `03-CAS-Swansea-sample.pdf` | [Swansea 大学指南](https://www.swansea.ac.uk/media/Guide-to-documents-for-Student-visa-application.pdf)第 10 页 | 已修复图片正文漏读；能读取 CAS 正文字段；占位姓名和号码保持未知 |

这些是大学公开的脱敏材料或教学模板；没有取得完整、经授权的真实客户案件数据。保留全部可见日期、金额和遮盖，不补造身份信息。页面抽取仅用于缩小阅读范围，不将指导文件转换为有效申请证据。

## 文件与来源

完整原文件保存在 `external-materials/public-samples/`，另有 [Sussex 银行流水](https://student.sussex.ac.uk/international/documents/bank-statement-notes.pdf)和[银行信模板](https://student.sussex.ac.uk/international/documents/example-bank-letter.pdf)。Sussex 流水触发 OCR，产生低置信度提示；银行信可以提取文字，但字段是待填写模板。

下载 URL、SHA-256、抽取页码和读取结果在本地 `external-materials/public-sources.json`。第三方 PDF 没有明确再分发许可，仅本地保存，Git 忽略；仓库保留来源链接和检查结论。

## 修复与剩余限制

`documents.read_document()` 现在检查页面中的图片对象（含嵌套 Form），对含图片页面渲染整页并执行 OCR，避免说明文字遮蔽材料正文；纯文字 PDF 仍直接提取。OCR 错误不会退回仅有说明文字的结果。含图片页的低置信度继续报告，不能等同于证据满足。小 logo 也会触发整页 OCR，是当前保守的性能取舍。

低置信度、倾斜图金额漏读、表格字段偶发遗漏仍存在。本次改善了读取覆盖，未证明全文无误或真实客户案件可以自动交付。
