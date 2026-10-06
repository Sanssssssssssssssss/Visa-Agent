# 双语信息表 / Bilingual worksheets

填写 `Information` 页 **C 列**，保存后回复邮件作为附件发送。`Documents` 页列材料和官方链接。实际邮件所附表格已绑定案件，优先使用它。此处通用空白表也能回传，邮箱线程决定归案，表内邮箱不能改变案件所有者。

Fill **column C**, save and reply with the workbook attached. Use the case-specific file emailed by the assistant when available. Generic blank forms below also work. Form answers do not replace passport or financial evidence.

| 路线 / Route | 空白 / Blank | 虚构测试例 / Fictional example |
|---|---|---|
| Visitor | [空白表](visitor-blank-zh-en.xlsx) | [测试例](visitor-example-TEST-ONLY.xlsx) |
| Student | [空白表](student-blank-zh-en.xlsx) | [测试例](student-example-TEST-ONLY.xlsx) |
| Skilled Worker | [空白表](skilled_worker-blank-zh-en.xlsx) | [测试例](skilled_worker-example-TEST-ONLY.xlsx) |

`TEST-ONLY`、`bad-` 文件仅供测试，不能用于实际申请 / Test files contain fictional data and must never be used for an actual application.

反例包含缺生日、不存在的生日、未来生日、邮箱错误、拒签史不确定、公式、护照号冲突和要求系统强行完成的提示注入。预期均不得直接完成；补齐生日、修正邮箱后可以继续。对应 PDF 在 `../materials/dev_visitor/`、`../materials/dev_student/`、`../materials/dev_skilled_worker/`，均有合成标记，仅明确创建的演示案件允许使用。

`*-answers.json` 是预先确定的答案，`manifest.json` 冻结哈希。`scripts/generate_intake_examples.py` 可重建素材；不要在验收中途重建覆盖失败。
