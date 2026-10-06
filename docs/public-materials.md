# 公开材料手动测试

2026-10-06 下载并检查。原有 6/6 真实模型验收使用自制合成材料，不能证明能处理这些公开文件。本轮只验证下载、PDF 版式和实际文档读取，没有新增模型调用。

本地可拖入的文件在 `external-materials/try-these/`。在网页右侧选择「空白案件」，每份文件单独开一个案件测试。它们来自不同的公开样例，不属于同一申请人；姓名、账号有遮盖或占位符，日期较旧，预期应保留未知并补问，不能直接交付。

| 文件 | 来源和处理 | 实际读取结果 |
|---|---|---|
| `01-Lloyds-statement-redacted.pdf` | [Bournemouth 大学指南](https://www.bournemouth.ac.uk/sites/default/files/asset/document/TIER-4-GENERAL-BANK-STATEMENT-CHECKLIST-v11JUN2018-2.pdf)第 2–4 页，保留原有脱敏和说明标记 | 3 页文本可读取；已目视核对版式，尚未验收模型字段/表格对应关系 |
| `02-BOC-deposit-redacted.pdf` | [Sussex 大学存款证明样例](https://student.sussex.ac.uk/international/documents/certificate-deposit-example.pdf)第 1 页 | **暴露漏读问题**：读取器选择 PDF 文本层，只得到部分标注和说明，未覆盖图片中的银行证明正文 |
| `03-CAS-Swansea-sample.pdf` | [Swansea 大学指南](https://www.swansea.ac.uk/media/Guide-to-documents-for-Student-visa-application.pdf)第 10 页 | **暴露漏读问题**：CAS 是嵌入图片，当前读取器只返回周围说明文字 |

这些是大学公开的脱敏材料或教学模板；没有取得完整、经授权的真实客户案件数据。保留全部可见日期、金额和遮盖，不补造身份信息。页面抽取仅用于缩小阅读范围，不将指导文件转换为有效申请证据。

## 文件与来源

完整原文件保存在 `external-materials/public-samples/`，另有 [Sussex 银行流水](https://student.sussex.ac.uk/international/documents/bank-statement-notes.pdf)和[银行信模板](https://student.sussex.ac.uk/international/documents/example-bank-letter.pdf)。Sussex 流水触发 OCR，产生低置信度提示；银行信可以提取文字，但字段是待填写模板。

下载 URL、SHA-256、抽取页码和读取结果在本地 `external-materials/public-sources.json`。第三方 PDF 没有明确再分发许可，仅本地保存，Git 忽略；仓库保留来源链接和检查结论。

## 当前缺口

`documents.read_document()` 以文本数量判断是否需要 OCR。有足够说明文字的混合 PDF 会跳过材料图片，且当前可能没有问题提示。上述两份文件复现了这个缺口，本轮尚未修复。不能把 `problems=[]` 当作整页内容完整，也不能把本轮试读计入原有模型验收通过数。
