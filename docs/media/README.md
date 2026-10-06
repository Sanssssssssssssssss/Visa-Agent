# Media provenance / 图片来源

- `logo.png`: generated for this project with the built-in image generation tool on 2026-10-07. Decorative branding; no UK government affiliation.
- `email-journey.png`: selected **verbatim** Chinese Visitor reply excerpts from [full-delivery-transcripts.md](../full-delivery-transcripts.md), typeset as a documentation figure. It is not a screenshot of Outlook or a shipped frontend. Dates and scope are shown in the image.
- `delivery-pack.png`: browser capture of `START-HERE.html` extracted from the committed [Visitor demo ZIP](../../examples/packs/visitor-demo.zip). The applicant and documents are synthetic; its demo notice remains visible.

邮件过程图是实际文本节选排版；材料包图是真实导出 HTML 的浏览器截图。没有把生成图片当成测试通过证据。第三方银行扫描页因许可未明确，没有放进 README。

To reproduce the evidence figures with a local Playwright CLI installation:

```sh
uv run python scripts/build_readme_media.py
npx --yes --package @playwright/cli playwright-cli -s=visa-docs open about:blank
npx --yes --package @playwright/cli playwright-cli -s=visa-docs run-code --filename output/readme-media/capture.js
npx --yes --package @playwright/cli playwright-cli -s=visa-docs close
```

Rendering is a documentation task; Node/Playwright are not required by the mail worker or offline test suite. Fonts/emoji appearance depend on the rendering OS.
