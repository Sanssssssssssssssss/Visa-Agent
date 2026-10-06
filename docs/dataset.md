# 数据集与来源

`datasets/freeze.json` 固定 15 个案件和 77 个文件的 SHA-256。种子为 `20261005`。案件输入在 `cases/`，答案在 `expected/`，实际 PDF/JPEG 在 `materials/`。答案由人工编写的字段和生成模板导出，未调用待测模型生成。

每个答案含最终状态、每事件状态、字段值、来源文件/消息和页码、必须出现的阻塞项。回放结束后才加载答案，模型没有读取答案文件的工具。验收比较事实和状态；回复措辞无需逐字匹配，应用最多提出三个问题。

| 场景 ID | 检查目标 |
|---|---|
| dev_visitor | 三轮补件后待复核，可独立批准 |
| dev_student | CAS、资金、TB 准备完成 |
| dev_skilled_worker | CoS、英语、TB，雇主维持费用承诺 |
| dev_ambiguous_route | 路线不足，询问 |
| dev_missing_document | 资金/工作材料缺失 |
| dev_unreadable_image | 空白图片明确不能通过 |
| dev_name_conflict | 姓名冲突转顾问 |
| dev_funds_period | 资金持有期间不足 |
| dev_missing_translation | 中文材料缺译文 |
| dev_duplicate_event | 重复事件与重复附件不重复改变版本 |
| dev_restart | 新建服务对象继续案件，另有真实 CLI 进程重启测试 |
| dev_stale_approval | 批准后改变事实，旧版本拒绝批准 |
| holdout_visitor | 不同姓名/日期/金额/排版，图片和 PDF 分批混合 |
| holdout_student | 资金覆盖期间不足，停在 WAIT_USER |
| holdout_skilled_worker | 先达到待复核，再换 CoS，保留冲突，经独立顾问拒绝旧材料后重新要求资金 |

所有材料都有 SYNTHETIC 标记、虚构机构与测试号码，不能用于实际申请。为了让调试可以直接核对，基础材料保留清晰字段标签；这比真实银行流水/证件版式简单。holdout 改变了字段顺序、布局、身份信息和数值，仍属于合成数据，不能推断生产准确率。

`materials/module/` 还包含银行信、行程、资助、ATAS、翻译声明，中英文文档、扫描 PDF、JPEG、旋转/模糊/裁切变体、缺页、损坏及加密 PDF。加密文件密码仅为公开合成测试字符串。模糊/裁切样例用于手动观察；不能把“读取了一个残页”当作检测了所有缺页。

## 官方依据

核对日期：2026-10-05 UTC / 2026-10-06 新加坡时间。运行规则固定在 `src/visa_agent/rules.py`，更新规则须新版本和复核。

| 来源 | 用途 |
|---|---|
| [Visitor supporting documents](https://www.gov.uk/government/publications/visitor-visa-guide-to-supporting-documents/guide-to-supporting-documents-visiting-the-uk) | 访问条件、支持材料、翻译声明 |
| [Student documents](https://www.gov.uk/student-visa/documents-you-must-provide) | CAS、证件、条件材料 |
| [Student money](https://www.gov.uk/student-visa/money) | 生活费、28 天/31 天、差异化证明 |
| [Financial evidence](https://www.gov.uk/guidance/financial-evidence-for-student-and-child-student-route-applicants) | 银行信/流水及财务字段 |
| [Skilled Worker documents](https://www.gov.uk/skilled-worker-visa/documents-you-must-provide) | CoS、雇主、职业及条件材料 |
| [Skilled Worker costs](https://www.gov.uk/skilled-worker-visa/how-much-it-costs) | GBP 1270、维持费用担保和期间 |
| [Skilled Worker English](https://www.gov.uk/skilled-worker-visa/knowledge-of-english) | 新申请 B2 与豁免边界 |
| [TB requirements](https://www.gov.uk/tb-test-visa) | 停留/居住历史及证明条件 |

浏览器研究工具已读取上述依据。`scripts/snapshot_sources.py` 尝试从本地 Python 保存完整网页快照时，本机到 GOV.UK 的 TLS 连接失败；真实错误保留在 `datasets/sources.json`，没有伪造下载成功或内容哈希。因此仓库保存链接和核对记录，未打包官方网页全文。

官方内容通常适用 [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)，具体第三方内容以原页标注为准。

## 公开版式参考

2026-10-06 已将下列大学原文件下载到本地，并补充 Bournemouth 脱敏流水。可直接拖入的摘页、操作方法及发现的漏读问题见[公开材料检查](public-materials.md)。本轮没有改动原冻结数据或验收答案。

- [Sussex 财务证明样例入口](https://student.sussex.ac.uk/international/visas/applying/proof)：银行流水、银行信和资助形式参考。
- [Swansea Student visa documents PDF](https://www.swansea.ac.uk/media/Guide-to-documents-for-Student-visa-application.pdf)：CAS 等版式参考，政策数值应以当前 GOV.UK 为准。
- [GOV.UK basic passport checks](https://www.gov.uk/government/publications/basic-passport-checks)：检查和版式参考，不作为外国申请人的有效护照模板。

再分发许可未确认，第三方 PDF 保存在已忽略的 `external-materials/`，仓库仅保留链接和检查结论。原自动验收使用的是仓库合成材料；后续公开文件试读发现了缺口，没有声称解析全面通过。

## 冻结与复现

```powershell
uv run visa-agent --mode offline verify-dataset
uv run visa-agent --mode offline replay datasets/cases/dev_student.json
```

新建基线时才运行 `uv run python scripts/generate_dataset.py --force`。普通文字 PDF/图片和字段可重复生成；加密 PDF 的加密初始化包含随机性，所以全目录字节不保证跨次生成完全相同。已提交的冻结文件是本次验收的唯一基线。不要用再生成代替哈希校验。

首次 Visitor 试跑使用初始基线；在最终 holdout 运行之前补齐了日期差异、逐轮来源断言和资助变更事件，重新冻结后运行正式六案。两个哈希均保留在验收记录，holdout 结果未用于重写预期答案。
