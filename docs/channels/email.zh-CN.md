# 发邮件亲自测试

[English](email.md) · [部署](../deployment.zh-CN.md) · [原始邮件记录](../full-delivery-transcripts.md)

先完成部署，确认 `scripts/mail_service.py status` 显示运行中。收件地址填**你配置的 Agent QQ 邮箱**，发件地址使用自己的其他邮箱。项目不提供公共托管邮箱。样例模式开启、HITL 关闭时，可用下面的虚构材料体验交付。

## 第一次咨询

新建邮件，主题可写 `Visa test - Visitor`，正文：

```text
你好，我想去英国旅游，第一次办签证，不知道从哪里开始。
```

预期：收到中文回复，了解来意、询问信息或材料、显示进度。路线明确后会附中英双语信息表。客户填表 C 列，保留字段名；不确定的内容留空，不能把“未知”写成“否”。收到回复所需时间包括 15 秒轮询间隔、OCR 和模型处理，不承诺固定延迟。

## 三条路线走到交付

下列文件均是清楚标注的测试样例，不能用于真实申请。每条路线开独立的新邮件线程，同一条路线后续使用邮件客户端的**回复**。

| 路线 | 首轮正文 | 第二轮附件（先交表和身份页） | 第三轮附件 |
|---|---|---|---|
| Visitor | 我想去英国旅游，需要准备些什么？ | `datasets/intake/visitor-example-TEST-ONLY.xlsx`；`datasets/formatted-materials-v2/visitor/identity.jpg` | 同目录 `funds-scan.pdf`、`work.jpg` |
| Student | 我拿到英国学校录取了，需要准备学生签证。 | `datasets/intake/student-example-TEST-ONLY.xlsx`；`datasets/formatted-materials-v2/student/identity.jpg` | 同目录 `funds-scan.pdf`、`school.jpg`、`health.jpg` |
| Skilled Worker | Hi, I have a UK job offer and need a Skilled Worker visa. What should I prepare? | `datasets/intake/skilled_worker-example-TEST-ONLY.xlsx`；`datasets/formatted-materials-v2/skilled_worker/identity.jpg` | 同目录 `sponsor.jpg`、`language.jpg`、`health.jpg` |

第二轮正文可写“表填好了，先发护照给你”；第三轮写“剩下的材料也整理好了，请看看还缺什么”。英文可写 “Here are the remaining documents. Is anything still missing?”。不要把三种签证、不同申请人的文件混在同一案件；一份材料的 PDF/JPEG 是不同格式变体，选一种即可。

预期状态从 `WAIT_USER` 继续到 `COMPLETE`，最终邮件附 `visa-materials.zip`。解压后看 `START-HERE.html`，核对原件、表格、缺项说明、来源和官网操作指引。模型可能提取失败或提出待确认问题；如未完成，应保存本轮记录，不能把预期结果当作实测结果。上述图片版 Visitor/Worker 已有真实 API 验收；Student 同内容第一版已验，第二版未单独重跑。三条真实邮箱完整验收使用的是较早的文字 PDF，详见[记录](../full-delivery.md)。

最快的 Visitor 检查：新邮件一次附上 Visitor 表、`identity.jpg`、`funds-scan.pdf`、`work.jpg` 四个文件。相同字节曾验证样例开关 ON 完成、OFF 等待补件，见[开关实测](../sample-switch.md)。

## 多邮箱和反例

| 操作 | 应观察到什么 |
|---|---|
| 用另一个发件邮箱发新邮件 | 新案件，不出现第一个人的姓名或材料 |
| 原邮箱回复 Agent 邮件 | 继续同一案件，保留已收资料 |
| 同一发件邮箱另起新邮件 | 新案件；主题相同不等于同一个线程 |
| 尝试从另一个邮箱接管原线程 | 拒绝不匹配的发件人 |
| 只发 `/status` | 查看当前材料进度，不调用模型 |
| 只发 `/reset` | 新建空白案，旧记录保留；当前样例开关在此时生效 |
| `/exit` 后再发材料 | 说明会话已结束；`/start` 才重新开始 |
| 发 `datasets/intake/bad-missing-birthday.xlsx` | 提示缺出生日期，不能完成 |
| 发 `bad-passport-conflict.xlsx` 与不一致的身份材料 | 冲突保留，不能静默覆盖 |
| 发 `datasets/document-quality/personal-notes.pdf` / `passport-notes.jpg` | 自述不能当成护照证明 |
| 关闭样例后，新线程提交完整样例 | 要求补充真实材料，不应输出完成 ZIP |

命令单独发，移除自动签名，别同时附文件。使用“添加附件”选择文件；签名图片、内嵌图片不作为申请材料。单封最多五附件、每文件 10 MB、PDF 20 页，邮件整体 25 MB。

## 在哪里查看模型每次回答

```sh
uv run visa-agent --data data/qq-test inspect <case_id>
uv run visa-agent --data data/qq-test trace <case_id>
uv run visa-agent --data data/qq-test events <case_id>
```

`qq-watch-last.json` 和 `worker.stdout.log` 可找到本轮案件 ID；`qq-previews/*.sent.eml` 是实际发送的 MIME。Trace 保存模型提取建议、引导建议、原文、检查和最终回复。里面可能含客户资料，请勿直接贴到公开 issue。

邮件地址格式校验、引用链和案件绑定不等于客户实名认证；当前未做完整发件人域认证。开放收件适合受控试用，模型费用由部署者承担。
