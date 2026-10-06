# 公开材料修复与压力测试

2026-10-06 执行。**混合 PDF 图片正文漏读已修复；49 项离线测试通过。12 轮真实处理消耗 23 次 API 请求，整体 9/12 满足预先固定的检查；字段修正后的 9 轮为 8/9。** 失败未删除，预期答案未随模型结果修改。

这是重复调用、文件变体和重复收件的稳定性检查，不是生产并发吞吐量测试，也不代表完整签证案件交付成功。

## 修改

- `documents.read_document()` 检查图片对象，含图片页面按整页可见内容 OCR，纯文字页保持文本提取。OCR 失败明确返回问题。
- 提取提示词明确银行流水期间、存款日期、证明出具日期与未来有效期的区别；存款证明分类为银行信。位置字段不再接受完整地址。
- `evidence.validate_value()` 规范化明确的位置与币种表达，拒绝遮盖值和模板占位符。未降低 OCR 置信度阈值。

## 输入与预期

三份[大学公开文件](../public-materials.md)，每份原始 PDF 重复 3 次；另加 Lloyds 扫描 PDF、CAS 扫描 PDF和中国银行倾斜 2° JPEG，各 1 次。每轮建立独立案件，调用实际 OCR、真实 `deepseek-flash`、SQLite 和业务检查。客户消息采用普通英文，没有自制字段标签。

[预期答案](../../datasets/public-stress.json)在模型试跑前编写。测试先冻结原件与变体 SHA-256；原始冻结清单保留在本地 `output/public-stress/frozen.json`。断言覆盖正文标记、材料分类、已接收字段值、禁止错误就绪/审批，以及重建服务后的同事件去重。原始姓名、CAS 号码等被遮盖或未填写，必须保持未知。

检查允许正确省略未知字段，因此「通过」不能解释为所有字段都提取齐全。存款证明的可见金额也不能证明资金可用或覆盖期合规。

## 实际结果

| 阶段 / 文件 | 次数 | 满足检查 | 发现 |
|---|---:|---:|---|
| 首轮：三份原始 PDF | 3 | 1 | 发现存款证明期间选错、位置字段值不符合接口；随后修正提示词和校验 |
| 修正后：中国银行原 PDF | 2 | 2 | 图片金额/日期可读取；已接受字段一致，最低余额保持未知 |
| 修正后：CAS 原 PDF | 2 | 2 | 图片正文可读取；占位姓名/号码未录入，两轮已接受字段一致 |
| 修正后：Lloyds 原 PDF | 2 | 2 | 日期、币种正确；其中一次省略最低余额，完整性仍有波动 |
| 修正后：Lloyds、CAS 扫描 PDF | 2 | 2 | 正文标记可读取；CAS 扫描版省略 sponsor_name |
| 修正后：中国银行倾斜 JPEG | 1 | 0 | `300,000.00` 未完整识别；币种候选被来源校验拒绝，状态为 NEEDS_HUMAN |

12 轮均没有服务异常或错误 COMPLETE/READY_FOR_REVIEW，没有自动审批。12 次持久化去重检查均未新增模型请求。低 OCR 置信度仍会阻止这些文件直接满足材料检查。

另通过实际 HTTP 接口进行 4 线程、12 次同时重复提交：只处理一次事件、版本增加一次、保留一份附件和一条运行记录。这个并发测试使用离线 FunctionModel；没有对真实 API 做并发负载测试。

## 用量与证据

- 真实请求 **23** 次：输入 **67,827 token**，输出 **5,274 token**；全部请求有用量记录。原先累计 32 次，本轮后为 **55/60**。
- 每轮端到端耗时中位数 **7.515 秒**，最慢 **12.391 秒**，包含 OCR、API 和状态写入。模型单价未配置，不估算费用。
- 本轮上限 24 次新增请求，包含工具循环和重试，使用原持久化请求账本；没有重置额度。
- [逐轮结果](../validation/public-stress.json)、[离线测试日志](../validation/pytest-public-stress.txt)。完整 OCR、模型工具记录和前后状态保存在本地 `output/public-stress/traces/`；第三方 PDF 与完整原文不上传仓库。
- [Linux CI](https://github.com/Sanssssssssssssssss/Visa-Agent/actions/runs/37453902398)已通过，验证代码提交 `600c454`。
- 原有 15 场景冻结哈希保持 `778242984890a6c7314eb52a3f84cfdbf7d94b1e7bf3afd1ba32802768ebf9a2`。

## 复现

先按[来源说明](../public-materials.md)准备同字节原件，运行以下命令；输出目录必须是未使用的新实验目录，脚本仍受原累计 60 次请求上限约束。

```powershell
uv run pytest -q
uv run python scripts/stress_public_materials.py prepare --output output/public-stress-new
uv run python scripts/stress_public_materials.py run --output output/public-stress-new --count 3
uv run python scripts/stress_public_materials.py run --output output/public-stress-new
```

同一目录继续运行会跳过已记录的轮次，包括失败轮次；不会通过自动重跑覆盖失败记录。
