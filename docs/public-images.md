# 公开扫描图片

本地图片位于 `external-materials/public-images/`，可以直接上传到本地测试页面。这些图片来自大学公开 PDF 的可见原页，保留脱敏遮盖、批注、金额和旧日期；不是本项目生成的申请人材料。公开来源不能证明原始客户或交易的真实性。

| 文件 | 内容与原始来源 |
|---|---|
| `01-BOC-deposit-redacted.png` | 中国银行存款证明扫描样例，中英文、印章；[Sussex 原 PDF](https://student.sussex.ac.uk/international/documents/certificate-deposit-example.pdf)，第 1 页 |
| `02-Lloyds-statement-page1.png` | Lloyds 银行流水首页；[Bournemouth 原 PDF](https://www.bournemouth.ac.uk/sites/default/files/asset/document/TIER-4-GENERAL-BANK-STATEMENT-CHECKLIST-v11JUN2018-2.pdf)，第 2 页 |
| `03-Lloyds-statement-page2.png` | 同一份流水的第 2 页，对应原 PDF 第 3 页 |
| `04-Lloyds-statement-page3.png` | 同一份流水的第 3 页，对应原 PDF 第 4 页 |

启动 `uv run python -m visa_agent.web --sample blank`，按终端地址打开页面。新建空白案件，先说清申请路线和目的；三张 Lloyds 图片一起上传。BOC 图片用另一个空白案件测试。被遮盖的姓名应保持未知或待确认，旧材料不能直接被当作本次申请的完整资金证明。这些样例适合检验读取和补件，不构成一套可以交付的完整申请材料。

图片由 `scripts/prepare_public_images.py` 渲染，180 DPI；整页渲染保留原有遮盖，不直接提取可能含隐藏信息的底图。来源页码及原 PDF、输出图片的 SHA-256 保存在本地 `SOURCES.json`。已人工查看 BOC 原页及 Lloyds 首页，未修改内容。

第三方文件再分发许可未确认，PDF 和图片只保存在被 Git 忽略的 `external-materials/`。复现时从上述链接下载 PDF，分别保存为 `external-materials/public-samples/02-deposit-certificate-Sussex.pdf` 和 `05-bank-statements-Bournemouth.pdf`，然后执行：

```powershell
uv run python scripts/prepare_public_images.py
```

脚本先核对已记录的源文件哈希。源站文件发生变化时会停止，需先核对新版内容。
