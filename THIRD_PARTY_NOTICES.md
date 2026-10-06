# Sources and reuse / 来源与复用

Original integration code is licensed under [MIT](LICENSE). Dependencies retain their own licenses; exact package versions are pinned in [uv.lock](uv.lock).

| Component | Actual use |
|---|---|
| [PydanticAI](https://github.com/pydantic/pydantic-ai) | Structured extraction, guidance, tools and offline FunctionModel/TestModel |
| [pypdf](https://github.com/py-pdf/pypdf) | PDF text reading |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | PDF rendering; its distribution includes PDFium and bundled notices |
| [RapidOCR](https://github.com/RapidAI/RapidOCR), [ONNX Runtime](https://github.com/microsoft/onnxruntime) | Local Chinese/English OCR |
| [Pillow](https://github.com/python-pillow/Pillow), [ReportLab](https://www.reportlab.com/opensource/) | Image handling and synthetic fixture generation |
| [openpyxl](https://openpyxl.readthedocs.io/) | Bilingual information worksheets |
| [MSAL](https://github.com/AzureAD/microsoft-authentication-library-for-python), [MSAL extensions](https://github.com/AzureAD/microsoft-authentication-extensions-for-python) | Outlook authentication adapter and OS-encrypted credential storage |
| Python standard library | IMAP, SMTP, MIME, SQLite, hashing and ZIP |

Design references: [Camunda KYC example](https://github.com/NPDeehan/camunda-8-kyc-agent-example), [DocProof](https://github.com/AppGambitStudio/DocProof), [LangChain agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch). They informed waiting, evidence layering and testing; their applications are not installed or vendored here. Chatwoot is a planned channel integration, not a runtime dependency. No claim is made that these references were production-ready visa engines.

Official UK guidance and public university materials retain their original rights. [Source inventory](datasets/sources.json), [dataset notes](docs/dataset.md) and [public image links](docs/public-images.md) record usage. Materials with unclear redistribution permission remain links/download instructions; original bank scans are not included in the repo.

The committed fixtures and demo packs are project-generated, fictional and labelled. [Media provenance](docs/media/README.md) distinguishes the generated logo, transcript figure and actual pack screenshot. None of the branding implies government endorsement.

本项目复用依赖和设计思路，但业务状态、规则、来源校验和发件记录由本仓库实现。第三方原始资料不自动适用本仓库 MIT 许可证。
