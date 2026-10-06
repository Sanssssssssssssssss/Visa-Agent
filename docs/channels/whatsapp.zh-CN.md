# WhatsApp 接入说明

[English](whatsapp.md) · [已验证的邮箱部署](../deployment.zh-CN.md)

**当前只实现本地 WhatsApp 会话模拟。** 仓库没有已上线的 webhook、Meta/Twilio 配置入口、媒体下载 worker 或 WhatsApp 发信接口。填一个手机号不能直接启用真实 WhatsApp。下面是后续接入设计及配置顺序。

## 复用 Chatwoot 渠道层

案件引擎保留在本项目，WhatsApp 收件箱和人工接管工作台交给 Chatwoot。[Agent Bot](https://www.chatwoot.com/features/chatbots) 可以将会话事件发往 HTTPS 回调，再由机器人调用 API 回信。先按[官方渠道指南](https://www.chatwoot.com/hc/user-guide/en/categories/other-channels)选定并连接 WhatsApp 服务商；业务账号、号码和验证要求以该服务商为准。

1. 建立 Chatwoot 账户或独立部署，连接专用测试号码。先验证“手机发消息 → Chatwoot 收到 → 人工回复手机”。
2. 实现有认证的 HTTPS 桥接和持久任务队列。webhook 先保存并快速应答，OCR/模型由 worker 处理，避免耗时超过回调期限。
3. 配置 Agent Bot 或 [`message_created` 订阅](https://developers.chatwoot.com/api-reference/webhooks/add-a-webhook)，绑定目标收件箱。过滤自己的 outgoing 消息和 private 内部备注，防止循环回信。
4. 按部署版本验证回调来源，约束 account/inbox；通过可信、有认证的接口下载媒体并执行大小限制。现有内部 HMAC 只是内部连接器约定，不能拿来验证 Meta/Twilio 签名。
5. 转为 `Incoming` 并调用同一个 `Inbox` / Case 引擎。下面是建议映射，落地时需以实际 payload 校验。

| 字段 | 桥接写入 |
|---|---|
| `channel` | `whatsapp` |
| `account` | 含 Chatwoot account 和 inbox ID 的命名空间 |
| `thread` | 稳定 conversation ID |
| `sender` | 服务商确认的完整 E.164 手机号码 |
| `message_id` | 稳定消息 ID，不能用时间戳代替 |
| 正文与附件 | 用户文本和下载到本地的文件 |

同线程绑定同发件人，邮箱和手机号不能自动合并。`/reset` 在同渠道会话中建立新案。当前 `receive_connector()` 只接受 Graph/IMAP，接 Chatwoot 时需增加明确的、已认证的 provider 入口。

## 回信与交付

桥接还需持久发件记录，复用 `mail_outbox.py` 中“发送前核对版本、结果不明不盲目重发”的业务原则。Chatwoot [发消息 API](https://developers.chatwoot.com/api-reference/messages/create-new-message) 路径为 `POST /api/v1/accounts/{account_id}/conversations/{conversation_id}/messages`，使用 `api_access_token`；对客户的文字回复设 `message_type=outgoing`、`private=false`，附件使用 multipart `attachments[]`。

底层 WhatsApp 的会话窗口、模板要求和可发送 MIME 类型需单独核对。不要假设邮件 ZIP 可以直接通过 WhatsApp 发送；带权限和过期时间的下载链接，或明确授权的邮件交付，需要另做实现与验收。当前不提供此下载服务。

若只想先验证服务商收发，[Twilio Sandbox](https://www.twilio.com/docs/whatsapp/sandbox)有加入测试号码和配置回调的流程；它是另一种渠道实验，回调格式与 Chatwoot 不同，目前也没有接入本项目。

## 当前可执行的验证

```sh
uv run visa-agent --mode offline receive --channel whatsapp --account wa-demo --sender +447700900123 --thread customer-a --message-id wa-1 --text "route: visitor"
uv run pytest tests/test_inbox.py -q
```

这只验证本地路由，不向真实手机发消息。真实接入验收至少包括：两个手机号隔离；重复事件只回复一次；图片/PDF 可读；重启后继续；伪造回调拒绝；会话窗口结束后按规则发送模板；客户实际拿到交付文件。保留失败和服务商回执，再更新仓库状态。

官方接口参考核对于 2026-10-07；此桥接设计不计入 QQ 邮件实测成绩。
