# 实际验收记录

执行时间：2026-10-05 UTC / 2026-10-06 新加坡时间。环境：Windows、Python 3.12.3，依赖见 `uv.lock`。

**离线 41 项测试通过，12 个开发场景回放通过；真实 API 六案通过。** 四个正常案件经脚本调用独立顾问入口后为 COMPLETE；两个负面案件按预期等待补件。这里没有真人移民顾问签字，不代表真实签证申请通过。

## 运行证据

- [真实六案完整断言](validation/live.json)，[最初 Visitor 试跑](validation/smoke.json)。
- [12 场景离线回放](validation/offline.json)，单元/边界测试命令 `uv run pytest -q`：41 passed，24.87 秒。
- [SDK 兼容性](validation/compatibility.json)，[中英文图片实际 OCR + 模型提取](validation/materials.json)。
- [完整请求账本与用量](validation/usage.json)，[源码、锁文件与数据哈希](validation/code-and-data-hashes.json)。
- [可解压的 Visitor 材料包](validation/sample-visitor.zip)。每个 live/smoke 案件的完整运行 JSON 以 `validation/trace-<case_id>.json` 保存，含真实提取和工具记录。`<REPO>` 替换了本机绝对路径。

## 六案结果

模型为 `deepseek-flash`，通过 PydanticAI 2.54.0 / OpenAI SDK 3.24.0 调用；关闭思考模式。读取使用 pypdf 6.19.0、PDFium 5.14.0、RapidOCR 3.9.2。客户消息固定脚本，模型响应真实，数据库与 ZIP 均实际写出。

| 案件 | 最终状态 | HTTP 请求 | 输入 token | 输出 token | 结果 |
|---|---|---:|---:|---:|---|
| dev_visitor | COMPLETE | 3 | 7,052 | 1,624 | 通过 |
| dev_student | COMPLETE | 3 | 7,408 | 1,800 | 通过 |
| dev_skilled_worker | COMPLETE | 4 | 10,907 | 1,812 | 通过 |
| holdout_visitor | COMPLETE | 4 | 10,176 | 1,839 | 通过 |
| holdout_student | WAIT_USER | 3 | 7,411 | 1,811 | 正确阻止资金期间不足 |
| holdout_skilled_worker | WAIT_USER | 5 | 13,576 | 2,252 | 更改 CoS 后保留冲突，经顾问处置旧材料后重新索要资金证明 |
| 合计 | | **22** | **56,530** | **11,138** | **6/6** |

表中请求是整个案件累计值，每事件仍不超过四次。holdout Skilled Worker 有四个客户事件和一次独立复核。正常案件三轮完成补件，批准动作由回放器以 `synthetic-test-adviser` 执行。

包括兼容性检查、失败尝试、Visitor smoke 和双语材料检查，总计 **32/60** 次预留请求。正式六案未发生服务失败；请求差异含工具补读。单价未配置，不报告估计金额。第一次 SDK 普通回复成功后，旧用量调用方式导致记录中断，这一次 token 用量未知；一次 HTTP 400 也没有 token 返回。请求总数均保留，没有按成功数伪装成总成本。

最终冻结数据哈希：`778242984890a6c7314eb52a3f84cfdbf7d94b1e7bf3afd1ba32802768ebf9a2`。
规则版本：`2026-10-05-9a48d3a4044e`。
Visitor smoke 使用早期数据哈希 `9eeb40213035c3c81189ec8d5fb843a49b4a55824c5f8886b8846c00b831ff7d`，没有运行 holdout。正式冻结前增加了独立日期、来源/逐轮状态断言及资助变化事件。

## 离线覆盖

| 部分 | 实际验证 |
|---|---|
| 文件读取 | 文字 PDF、扫描 PDF、英文图片、中文图片、旋转图片；损坏、加密、10 MB/20 页/五附件边界 |
| 字段来源 | 空缺不通过、文件与自述分开、摘录和值不符拒绝、低置信度阻止、否定语句不能抽成肯定 |
| 规则 | 过期护照、姓名冲突、翻译缺失、Student 期间和差异化条件、银行信替代仍需完整字段 |
| 持久化 | 重复事件/附件、同 ID 改内容拒绝、真实 CLI 进程重启、失败回滚与重试 |
| Agent | FunctionModel 确定行为、TestModel 接线、四请求预算、重复工具停止、错误参数/跨案访问失败、提示注入无法授予审批权限 |
| 复核/交付 | 无法跳过阻塞项、旧审批失效、规则变更使批准失效、ZIP 篡改拒绝、清单/原件可打开 |

pytest 中 `ALLOW_MODEL_REQUESTS=False`，因此离线失败不会隐式改为付费调用。CI 也只执行这些离线检查。

## 遇到并修复的问题

1. SDK 当前依赖 `httpx2`，旧 `httpx` 导入不存在；按安装后的实际接口修复，并把直接依赖写入锁文件。
2. PydanticAI 当前 `result.usage` 是属性，旧的 `usage()` 调用在第一条真实回复后失败。后续全部修正；保留这次未知 token 的限制。
3. DeepSeek 默认思考模式拒绝 SDK 使用的强制结构化工具选择，返回真实 HTTP 400。按 [官方思考模式参数](https://api-docs.deepseek.com/guides/thinking_mode/) 显式关闭后，普通输出、结构化输出和读取工具检查通过。
4. GOV.UK 本地网页快照请求遇到 TLS EOF，失败记录保留在 `datasets/sources.json`；通过浏览器研究工具核对官方页面，未宣称下载成功。
5. 大型 wheel 连续下载缓慢；本地分段获取后逐个核对锁文件 SHA-256，最终 `uv sync --locked --offline` 成功。项目安装配置仍使用正常 uv 流程。

## 人工体验和剩余限制

开发期间实际打开并检查了中英文合成图片和浏览器中的材料报告，确认文字可见、报告可浏览、原件链接和 ZIP 内容一致；这属于开发检查。真人顾问的业务确认仍应由使用者通过 `review` 完成。测试中的脚本批准不能替代这一步。

本次覆盖是清晰标签为主的合成材料；未测真实护照防伪、真实银行逐笔对账、大规模模糊照片或长期客户对话。字段摘录可定位不等于语义绝对正确，模型自报 confidence 没有做统计校准。公开大学 PDF 仅作为版式来源，未纳入此次解析验收。

CLI 模拟收件，尚无 WhatsApp/email、顾问 UI、身份鉴权或并发服务。客户回复采用最多三条问题的规则模板。未覆盖的专业分支必须完善规则或转交真实顾问处理，不能通过模型猜测填齐。

CI 结果以仓库 Actions 的最终提交运行记录为准。本地用量和真实 API 结果不等同于 Linux CI 的结果，也不代表生产准确率。
