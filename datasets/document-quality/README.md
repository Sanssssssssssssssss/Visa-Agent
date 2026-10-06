# 故意自写的材料反例

这里全部是虚构内容，用于重现“随便写几个字段也被当作证明”的缺陷。PDF 故意没有测试水印，不能用于申请；源文件哈希及用途见 `manifest.json`。`plain-language.pdf` 是后加的普通英文标签反例，哈希记录在每次实验的 `extra_input_hashes`。

发新邮件给已配置的 Agent 邮箱，写“你好，我去英国旅游，表和材料放附件了”，附：

1. `completed-information.xlsx`：填好的虚构申请信息表。
2. `plain-language.pdf` 或 `passport.pdf`：自写护照字段。
3. `bank.pdf`：自写银行字段。
4. `employment.pdf`：自写雇主字段。

预期：信息表可以记录，三类证明仍需提供，状态 `WAIT_USER`，不发完成 ZIP。`personal-notes.pdf` 测自述段落，`passport-notes.jpg` 测文字截图；后者也不应成为护照。

运行和实际回复见 [材料接受条件复测](../../docs/document-quality.md)。
