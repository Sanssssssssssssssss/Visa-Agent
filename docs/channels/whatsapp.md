# WhatsApp integration path

[简体中文](whatsapp.zh-CN.md) · [Verified email setup](../deployment.md)

**Current status: local WhatsApp conversation simulation only.** There is no public webhook, Meta/Twilio credential configuration, media download worker or WhatsApp outbound delivery in this repository. Setting a phone number cannot enable live WhatsApp. The following is an implementation guide for a future connector, not a completed deployment receipt.

## Reuse Chatwoot for the channel

Keep the case engine here; let Chatwoot manage the WhatsApp inbox and human conversation workspace. Its [Agent Bot interface](https://www.chatwoot.com/features/chatbots) forwards incoming events to your HTTPS endpoint and accepts outgoing replies through its API. Configure a supported WhatsApp provider in Chatwoot using its [current channel guides](https://www.chatwoot.com/hc/user-guide/en/categories/other-channels). Provider account, number and verification requirements depend on the chosen provider.

1. Create a Chatwoot account or deploy it separately; connect a dedicated WhatsApp test number. Prove phone → Chatwoot → manual reply before adding an AI bridge.
2. Implement an authenticated HTTPS bridge with a durable event queue. Acknowledge accepted events quickly; OCR/model calls run in a worker. Do not run a long model turn inside the provider webhook timeout.
3. Configure an Agent Bot or a [message-created webhook subscription](https://developers.chatwoot.com/api-reference/webhooks/add-a-webhook), then bind it to the intended inbox. Ignore outgoing messages and private agent notes to prevent reply loops.
4. Authenticate the deployed provider/Chatwoot handoff, restrict account/inbox IDs, fetch media only through trusted authenticated endpoints, and enforce this project's file limits. The existing internal HMAC helper is **not** a Meta/Twilio signature verifier.
5. Map the verified event into `Incoming`, then invoke `Inbox` and the shared case engine. A proposed mapping is below; validate it against the deployed Chatwoot version's actual payload.

| Case routing field | Bridge value |
|---|---|
| `channel` | `whatsapp` |
| `account` | Namespace containing Chatwoot account + inbox ID |
| `thread` | Stable Chatwoot conversation ID |
| `sender` | Provider-verified complete E.164 phone number |
| `message_id` | Stable provider/Chatwoot message ID, never the timestamp |
| `text`, attachments | Customer content and staged local files |

The sender is pinned to its conversation. An email and a phone number are not automatically merged. Reset creates a new case generation in the same channel session. The existing `receive_connector()` only accepts Graph and IMAP; add an explicit authenticated provider boundary before wiring Chatwoot into it.

## Reply and deliver

The bridge needs a durable outbox with the same stale-version and ambiguous-send behavior as `mail_outbox.py`. Chatwoot's [message API](https://developers.chatwoot.com/api-reference/messages/create-new-message) uses `POST /api/v1/accounts/{account_id}/conversations/{conversation_id}/messages` with an `api_access_token`; send text as `outgoing` with `private=false`. File requests use multipart `attachments[]`.

Check the underlying WhatsApp provider's session/template rules and allowed MIME types. Do not assume the email ZIP can be delivered directly through WhatsApp. A separately secured, expiring download link or explicit email delivery needs its own implementation and end-to-end test. No such link service is bundled here.

For a provider-only experiment, [Twilio Sandbox](https://www.twilio.com/docs/whatsapp/sandbox) documents joining the test number and setting an inbound callback. It is an alternative channel experiment; its webhook contract differs from Chatwoot's and is not wired into this project.

## What runs today

```sh
uv run visa-agent --mode offline receive --channel whatsapp --account wa-demo --sender +447700900123 --thread customer-a --message-id wa-1 --text "route: visitor"
uv run pytest tests/test_inbox.py -q
```

This exercises local routing only and sends no WhatsApp message. Before claiming a live connector: verify two real phones remain isolated; duplicate delivery causes one response; image/PDF uploads survive restarts; forged events are rejected; a closed messaging window uses the correct template; and the customer can retrieve the delivered files. Preserve failures and provider receipts.

Official API references checked 2026-10-07. The proposed bridge is not part of the reported QQ delivery results.
