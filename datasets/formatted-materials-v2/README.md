# 合成图片与扫描 PDF

这 33 个文件使用虚构信息，均有测试标记，**不是正常客户的真实材料**。身份页只是文字版式，未模拟真实护照的照片、安全特征或证件版式。公开银行扫描原页见[另一个来源目录](../../docs/public-images.md)。

每路线含原始文字 `.pdf`、可直接查看的 `.jpg` 和只有页面图像的 `-scan.pdf`。用于确认 PDF 渲染、OCR、模型来源提取及 ZIP 交付。普通邮箱案件不能靠这些测试材料完成；脚本在本机明确创建演示案件。

```powershell
uv run python scripts/full_delivery_acceptance.py --output output/my-images --formatted --materials datasets/formatted-materials-v2
```

运行需要真实 API。Visitor/Worker 本轮已用此目录完成；Student 在第一版同内容输入上已完成，第二版未重复运行。第一版失败不覆盖。`manifest.json` 保存冻结哈希；生成器拒绝覆盖已有清单，另设 `--output` 才能重新生成。
