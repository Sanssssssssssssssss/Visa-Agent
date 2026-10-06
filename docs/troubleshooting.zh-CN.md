# 故障排查

[English](troubleshooting.md) · [配置参考](configuration.zh-CN.md) · [邮件逐轮测试](channels/email.zh-CN.md)

按收件、案件处理、发件的顺序定位。收到回复不代表案件完成；`COMPLETE` 也不代表已经向 UKVI 提交。

## 没有收到回复

```sh
uv run python scripts/mail_service.py status
```

容器部署查看：

```sh
docker compose ps
docker compose logs --tail 30 agent
docker compose exec agent python -m visa_agent.qq_mail status --data /data
```

检查 `running`、`last_poll.at` 和 `last_poll.error_type`。OCR 与模型处理期间轮询时间戳会暂时变旧；本机必须保持联网且不休眠。检查客户垃圾箱、Agent 的 INBOX；当前连接器不扫描其他文件夹。

| 现象 | 下一步 |
|---|---|
| 进程已停止 | 看 `worker.stderr.log`，修正模型/邮箱凭证，按部署指南重启 |
| 运行中但没处理来信 | 邮件是否晚于配置的 `since`、收件地址是否正确、是否进 INBOX；开放收件应有 `accept_all=true`、`require_tag=false` |
| 发件人被拒绝 | 看 `qq-rejections/`；From/Reply-To 不一致、引用别人线程、自动回信不按新客户处理 |
| 处理失败 | 在 `qq-watch-last.json` 或 `worker.stdout.log` 找 case ID，再查 trace |
| 发件是 `retry` | SMTP 尚未确认；持久队列保留 Message-ID 并退避重试 |
| 发件是 `sent` | SMTP 接受；不保证已进客户收件箱或已读 |

`python -m visa_agent.qq_mail probe --data <目录>` 检查 IMAP/SMTP 登录，不向客户发信。网络故障保留游标；不要为排查超时启动第二个 worker 或删除持久数据。

## “交了三个文件，为什么只核对两个？”

收到的文件、证明类别、已核对的要求是不同计数。信息表单独统计；同份材料的 PDF/JPEG 变体不是两种必需材料，相同字节会去重。

例如 Student 已交护照、银行、TB 三类，可以显示 **收到 3/4、核对 2/4**。缺 CAS 时，银行文件仍保留，但需要学费、课程月数和学习地点才能算所需资金。缺 CAS 不等于资金文件没收到，也不应催重传。[实际修复与模型回放](finance-receipt.md)。

```sh
uv run visa-agent --data data/qq-test inspect CASE_ID
uv run visa-agent --data data/qq-test trace CASE_ID
uv run visa-agent --data data/qq-test events CASE_ID
```

容器在命令前加 `docker compose exec agent`，目录用 `--data /data`。依次核对文件名/哈希与 `problems`、已接受字段、`unconfirmed_candidates`、规则 `fail/unknown`、`customer_reply`。`bank_extraction_recheck` 记录漏字段重查，不会凭空补银行名。

## 材料到了但仍未完成

| 现象 | 原因与处理 |
|---|---|
| 样例被拒绝 | 操作者开启样例模式后，新建线程或 `/reset`；客户邮件不能切换模式 |
| 自己写的字段清单 | 可以提供申请信息，但不能替代护照、银行等证明 |
| 不清晰、缺页或未读完 | 提交清晰完整的支持格式文件；保留失败和页码记录 |
| 姓名或金额冲突 | 两份来源都保留，解决冲突，不能直接覆盖 |
| 表格仍缺信息 | 补 C 列缺项，保留字段名；填写真实日期，不确定的留空 |
| 关闭 HITL 仍 `NEEDS_HUMAN` | 冲突或业务分支未覆盖；取消最终复核不会补齐规则实现 |
| `BLOCKED` | 本轮处理失败；错误 trace 保留原事件供排查 |
| 完成却没有 ZIP | 看 `pack_path` 和发送 MIME；超过 18 MB 时本机保存并在邮件说明 |

正常正文来自模型的 `Guidance.reply`。工具/模型异常时，应用保留非空服务通知并记录失败；这能保证有待发送内容，不能保证网络可用或 SMTP 成功。[异常恢复测试](conversation-repair.md)。

## 清空对话和语言

在原线程仅回复 `/reset` 新建空白案件，`/exit` 关闭，`/start` 新开案，`/status` 查进度。命令去掉签名和附件。重置后旧案不进入新上下文，但审计不会删除。

模型跟随客户当前中文或英文消息；信息表和交付指引为双语，附件不决定回复语言。新建邮件线程会新建案件，即使主题与旧邮件相同。

## 报告问题时附什么

使用[问题模板](../.github/ISSUE_TEMPLATE/bug_report.yml)，提供 commit、系统、本机/容器模式、不含秘密的相关设置、预期/实际状态和合成复现文件。run/case ID 与原始 trace 留在本机；公开截图或日志移除客户姓名、地址、材料和凭证。

代码修改先跑 [TESTING.md](../TESTING.md) 中对应测试，再完成 [CONTRIBUTING.md](../CONTRIBUTING.md) 要求的检查。真实调用用于验证实际改动的模型行为；失败响应不能替换成模拟成功。
