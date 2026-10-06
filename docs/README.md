# Documentation / 文档

[Project overview](../README.md) · [项目首页](../README.zh-CN.md) · [Tests and receipts](../TESTING.md)

Visa Agent collects application information and documents through email, then returns a ZIP. Choose the task you want to complete. Guides describe the current implementation; dated reports preserve the versions and failures actually tested.

Visa Agent 通过邮件收集申请信息与材料，再把 ZIP 发回客户。按下面的用途阅读即可；部署指南描述当前操作，验收报告保留各次实验的版本与失败记录。

## Get a working example / 先跑起来

| Your task / 你要做什么 | English | 简体中文 |
|---|---|---|
| Run without model keys / 无密钥体验流程 | [CLI quickstart](../README.md#local-cli-demo) | [本机回放](../README.zh-CN.md#本机-cli-回放) |
| Start a persistent email service / 常驻邮箱服务 | [Docker deployment](docker.md) | [Docker 部署](docker.zh-CN.md) |
| Use Windows directly / Windows 本机运行 | [Native deployment](deployment.md) | [部署与启停](deployment.zh-CN.md) |
| Send emails and collect a ZIP / 发邮件走到交付 | [Three-route walkthrough](channels/email.md) | [三路线逐轮测试](channels/email.zh-CN.md) |

The email walkthrough includes first messages, pre-filled worksheets, exact image/PDF filenames, expected states, reset commands and negative cases. New inboxes accept any customer address and subject by default. No project web page or customer registration is required.

邮件教程包含首轮正文、已填表格、图片/PDF 文件名、状态变化、重置命令和反例。新部署默认接受任意客户邮箱与邮件主题，客户直接发邮件即可。

## Understand and change the code / 理解与修改

| Question / 要找的内容 | English | 简体中文 |
|---|---|---|
| Who decides what, and why? / 模型与代码如何分工 | [Architecture](architecture.md) | [架构与稳定性](architecture.zh-CN.md) |
| Which functions process a message? / 一封消息经过哪些函数 | [Code walkthrough](implementation.en.md) | [实现与调试](implementation.md) |
| Which values can I configure? / 参数、默认值与生效时间 | [Configuration reference](configuration.md) | [配置参考](configuration.zh-CN.md) |
| Why is a file still pending? / 不回信、材料待确认等问题 | [Troubleshooting](troubleshooting.md) | [故障排查](troubleshooting.zh-CN.md) |
| What would WhatsApp require? / 后续 WhatsApp 接入 | [Integration boundary](channels/whatsapp.md) | [接入边界](channels/whatsapp.zh-CN.md) |

## Verify the claims / 查看证据

| Claim / 能力 | Evidence / 记录 |
|---|---|
| Real email delivery of three packs / 三路线真实邮箱交付 | [Delivery and downloads](full-delivery.md), [recorded replies](full-delivery-transcripts.md), [downloadable ZIPs](../examples/packs/) |
| Model-written guidance and v2 scan cases / 模型回复与新版扫描件 | [Conversation repair](conversation-repair.md), [usage and failures](validation/conversation-reply.json) |
| Three received files versus two checked categories / 接收数量与核对数量 | [Finance receipt fix](finance-receipt.md), [model replay](validation/finance-receipt.json) |
| Open intake, thread isolation, restart and failure replies / 开放收件、隔离、恢复和异常回信 | [Test map](../TESTING.md), [mail regressions](../tests/test_qq_mail.py) |
| Linux image, OCR, persistence, backup and stop / 容器验收 | [Container acceptance](container-acceptance.md), [CI workflow](../.github/workflows/container.yml) |
| Rejection of self-written evidence and sample controls / 自述材料拒绝与样例开关 | [Document quality](document-quality.md), [sample ON/OFF receipt](sample-switch.md) |
| Behavioral regressions / 行为回归 | [Contracts and first divergence](behavior-regression.md), [record](validation/behavior-regression.json) |

Offline tests, model API replays and real mailbox journeys test different boundaries. Passing a synthetic case does not establish document authenticity, complete visa eligibility or production capacity. [TESTING.md](../TESTING.md) explains how to reproduce each type.

离线测试、真实模型回放、真实邮箱收发分别验证不同边界。合成案件通过不能证明材料真伪、完整签证资格或生产吞吐；复现命令见 [TESTING.md](../TESTING.md)。

## Materials, sources and maintenance / 数据、来源与维护

- [Application worksheet / 信息表](application-information.md), [frozen dataset / 冻结数据](dataset.md), [image fixtures / 图片样例](../datasets/formatted-materials-v2/README.md).
- [Public materials](public-materials.md), [public image sources](public-images.md), [media provenance](media/README.md), [third-party notices](../THIRD_PARTY_NOTICES.md).
- [Contributing](../CONTRIBUTING.md), [security and private data](../SECURITY.md), [changes](../CHANGELOG.md).
- [Historical experiments](history/README.md), [machine-readable receipts](validation/). Full customer traces remain in ignored local storage.

Navigation follows the task-oriented guides and references in [uv](https://docs.astral.sh/uv/); runnable examples follow [PydanticAI's README](https://github.com/pydantic/pydantic-ai#what-are-you-building). [Chatwoot](https://github.com/chatwoot/chatwoot#documentation) informed the visible demo and deployment/help links. These are documentation references; this repository keeps its existing runtime.
