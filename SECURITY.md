# Security and data boundaries / 数据边界

This is a local/single-operator pilot. Treat `data/` and `output/` as private: they can contain original documents, extracted personal information, model prompts, raw mail and reply records. Model processing sends selected text/images to the configured API provider. Choose a provider and retention policy appropriate to your applicants before using real personal data.

QQ credentials use encrypted OS persistence on desktop, or a private environment file on headless servers. Never put credentials in issues, command examples, screenshots or committed test receipts. The repository's examples use fictional applicants.

Mail routing checks address syntax, sender/thread binding, duplicate IDs and reply headers. It is not complete sender authentication, anti-spam or antivirus protection. Open intake can incur model costs. Do not expose the local inspector or internal connector directly on the public internet.

Unknown rules, unreadable files and conflicts block completion. These controls do not authenticate passports, bank documents or translation credentials. Sample mode is for demonstrations and must be visible in the output.

To report a vulnerability, use GitHub's **Report a vulnerability** control if it is available. Otherwise open an issue asking for a private reporting channel, without exploit details, applicant data or secrets. Only the current default branch is maintained; there is no response-time commitment.

安全问题请通过仓库的私密报告入口反馈；若入口不可用，先发不含敏感细节的联络请求。客户材料、原始邮件、密钥和可复现攻击细节不要直接放进公开 issue。
