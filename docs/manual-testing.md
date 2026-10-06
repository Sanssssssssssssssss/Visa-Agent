# 亲自测试 Visa Agent

**直接拖文件：** 运行 `uv run python -m visa_agent.web`，打开 <http://127.0.0.1:8765>。默认是真实模型、空白案件；先输入申请情况，再上传自己的文件或[公开扫描图片](public-images.md)。只有主动选择右侧合成演示场景，才会载入虚构背景及对应 `datasets/materials/` 测试文件。达到待复核后，先查看报告，再勾选确认并批准。网页复用已有 `data/` 请求账本和案件引擎，每个服务进程是一份本地工作区，刷新页面继续当前案件，重启服务创建新案件。

下面保留逐条 CLI 操作，供调试时使用。

在 VS Code 按 **Ctrl+Shift+V** 预览本文；菜单 **终端 → 新建终端**，选择 PowerShell。
当前产品是 CLI，每个命令模拟一条消息或一次上传。建议按下面顺序逐段执行，观察结果后再继续。

## 1. 准备终端

当前电脑的独立环境已经安装好，直接使用它即可：

```powershell
Set-Location 'E:\GPTProject2\Visa-Agent'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$visa = '.\.venv\Scripts\visa-agent.exe'
$visaArgs = @('--data', 'data/manual-offline', '--mode', 'offline')
& $visa @visaArgs verify-dataset
```

应显示 `"verified": true`。`offline` 不调用真实模型，通过合成材料的字段标签走业务流程。你的手动案件保存在 `data/manual-offline/`。

## 2. 亲手分批上传 Visitor 材料

创建新案件，读取现成客户的初始信息。每次重新开始都会生成新 ID：

```powershell
$visaCaseId = 'manual-visitor-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$visaScenario = Get-Content 'datasets/cases/dev_visitor.json' -Raw -Encoding UTF8 | ConvertFrom-Json
& $visa @visaArgs new $visaCaseId
& $visa @visaArgs message $visaCaseId $visaScenario.events[0].text --event-id intro
```

看输出的 `status` 和 `reply`：应为 `WAIT_USER`，提出补件问题。此时没有上传任何文件。

先上传身份页：

```powershell
& $visa @visaArgs attach $visaCaseId 'datasets/materials/dev_visitor/identity.pdf' --event-id identity
```

应继续 `WAIT_USER`，缺少工作和资金材料。再上传银行流水：

```powershell
& $visa @visaArgs attach $visaCaseId 'datasets/materials/dev_visitor/funds.pdf' --event-id funds
```

仍应等待在职材料。最后上传在职证明：

```powershell
& $visa @visaArgs attach $visaCaseId 'datasets/materials/dev_visitor/work.pdf' --event-id work
```

应变为 `READY_FOR_REVIEW`，返回 `pack_path`。**此时还没有批准。** 这次人为拆成四个事件，案件版本通常为 4；不要照抄其他案例的版本号。

## 3. 查看材料包，然后自己批准

```powershell
$visaCase = & $visa @visaArgs inspect $visaCaseId | ConvertFrom-Json
$visaCase | Select-Object id, version, status, pack_path
$visaCase.checks | Where-Object { $_.status -in @('fail', 'unknown') } | Format-Table id, status, message -Wrap
```

待复核时，最后一个命令应没有阻塞项。打开已生成的 HTML 报告：

```powershell
if (-not $visaCase.pack_path) { throw '尚未生成材料包，请先检查阻塞项。' }
$visaPackDir = [System.IO.Path]::ChangeExtension($visaCase.pack_path, $null)
Invoke-Item (Join-Path $visaPackDir 'report.html')
```

在报告中核对：姓名 `Lin Example`、最低余额 `40000 GBP`、各字段引用的文件/页码和原文，以及原件链接是否能打开。ZIP 也在 `pack_path` 指定的位置，解压后可单独浏览。

确认这套合成材料后，由你在终端执行批准：

```powershell
& $visa @visaArgs review $visaCaseId --version $visaCase.version --decision approve --reviewer manual-tester --notes '本人已核对这套合成测试材料及来源'
```

应得到 `COMPLETE` 和审批记录。这是测试材料的确认，不是给真实申请做专业签证审查。

再试一次批准后更改事实：

```powershell
& $visa @visaArgs message $visaCaseId 'trip_budget: 4000' --event-id changed-budget
$visaCase = & $visa @visaArgs inspect $visaCaseId | ConvertFrom-Json
$visaCase | Select-Object version, status, approval
```

旧审批应清空；新旧预算同时保留并触发冲突，案件进入 `NEEDS_HUMAN`。不能静默用新值覆盖。

## 4. 哪些文件可以直接拿来测

同一案例内的材料配套使用，混用不同申请人的材料会触发姓名冲突。

| 文件/目录 | 内容 | 怎么用 |
|---|---|---|
| [dev_visitor/](../datasets/materials/dev_visitor/) | `identity.pdf` 身份页、`funds.pdf` 流水、`work.pdf` 在职证明 | 按上面四步分批上传 |
| [dev_student/](../datasets/materials/dev_student/) | `identity.pdf`、`funds.pdf`、`school.pdf` CAS 信息、`health.pdf` TB 信息 | 配合 `cases/dev_student.json` 的初始客户信息 |
| [dev_skilled_worker/](../datasets/materials/dev_skilled_worker/) | `identity.pdf`、`sponsor.pdf` CoS、`language.pdf` 英语、`health.pdf` TB | 配合 `cases/dev_skilled_worker.json`；此例有雇主维持费用承诺 |
| [module/scan.pdf](../datasets/materials/module/scan.pdf) | 图片构成的扫描 PDF | `read` 应实际走 OCR |
| [module/photo.jpg](../datasets/materials/module/photo.jpg)、[rotate.jpg](../datasets/materials/module/rotate.jpg) | 英文身份页图片、旋转变体 | 查看识别文字、日期和置信度 |
| [module/chinese.jpg](../datasets/materials/module/chinese.jpg)、[chinese.pdf](../datasets/materials/module/chinese.pdf) | 中文测试材料 | 单独查看中英文读取结果 |
| [module/blur.jpg](../datasets/materials/module/blur.jpg)、[crop.jpg](../datasets/materials/module/crop.jpg) | 模糊、裁切图片 | 观察提取损失；未保证每个变体都自动识别出缺页 |
| [variants/unreadable.jpg](../datasets/materials/variants/unreadable.jpg) | 空白不可读图片 | 应出现读取问题，不能满足证件要求 |
| [variants/different_identity.pdf](../datasets/materials/variants/different_identity.pdf) | 姓名不同的身份页 | 在姓名冲突场景中应转人工 |
| [variants/short_period.pdf](../datasets/materials/variants/short_period.pdf) | Mei Example 的短期间资金证明 | 配套 Student 案件应被资金检查阻止 |
| [variants/chinese_employment.pdf](../datasets/materials/variants/chinese_employment.pdf) | Lin Example 的中文工作材料 | 缺译文场景应等待翻译 |
| [module/corrupt.pdf](../datasets/materials/module/corrupt.pdf)、[encrypted.pdf](../datasets/materials/module/encrypted.pdf) | 损坏和加密 PDF | 应返回明确的 `problems` |

这些全是合成材料。单独测试文件读取不需要调用模型：

```powershell
& $visa @visaArgs read 'datasets/materials/module/scan.pdf'
& $visa @visaArgs read 'datasets/materials/module/chinese.jpg'
& $visa @visaArgs read 'datasets/materials/module/corrupt.pdf'
```

看 `pages[].text`、`pages[].method`、`confidence`、`problems`。**读到文字只代表读取成功，不代表材料通过业务检查。** `read` 不会给案件补材料；要加入案件必须用 `attach`。

## 5. 一条命令观察异常场景

```powershell
& $visa @visaArgs replay 'datasets/cases/dev_name_conflict.json'
& $visa @visaArgs replay 'datasets/cases/dev_funds_period.json'
& $visa @visaArgs replay 'datasets/cases/dev_missing_translation.json'
& $visa @visaArgs replay 'datasets/cases/dev_unreadable_image.json'
```

依次应为 `NEEDS_HUMAN`、`WAIT_USER`、`WAIT_USER`、`WAIT_USER`。这里 `passed: true` 表示停在预期位置，并非已经完成材料交付。

正常 Student/Skilled Worker 可同样回放：

```powershell
& $visa @visaArgs replay 'datasets/cases/dev_student.json'
& $visa @visaArgs replay 'datasets/cases/dev_skilled_worker.json'
```

不加 `--approve-demo`，正常场景停在 `READY_FOR_REVIEW` 供你查看。回放结果的 `case_id` 是新案件 ID，不是前面的 `$visaCaseId`。
`dev_stale_approval` 和 `holdout_skilled_worker` 内含专门的脚本复核动作，适合观察机制；不要把它们当作完全由你操作的复核测试。`accept` 也会自动执行测试审批。

## 6. 切到真实模型，自己用自然语言聊

真实模式需要终端能读取到模型密钥。下面只显示是否存在，不打印密钥：

```powershell
[bool]($env:DEEPSEEK_API_KEY -or $env:VISA_API_KEY)
```

若显示 `False`，用隐藏输入录入已有 API 密钥：

```powershell
$env:VISA_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'API key' -AsSecureString)).Password
```

切换模式和存储目录，再建立一个全新案件：

```powershell
$env:VISA_MODEL = 'deepseek-flash'
$env:VISA_BASE_URL = 'https://api.deepseek.com'
$visaArgs = @('--data', 'data', '--mode', 'live')
$visaCaseId = 'manual-live-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
& $visa @visaArgs new $visaCaseId
& $visa @visaArgs message $visaCaseId '我叫 Lin Example，中国籍，今年30岁，住在中国，想去英国旅游，请告诉我需要准备什么。' --event-id intro
```

查看 `reply`，然后用新事件 ID 回答它的问题：

```powershell
& $visa @visaArgs message $visaCaseId '这里换成你对上一轮问题的回答' --event-id answer-1
& $visa @visaArgs attach $visaCaseId 'datasets/materials/dev_visitor/identity.pdf' --event-id identity
```

自然语言输入尚未有完整验收保证：观察它是否正确理解、是否还在重复询问、是否编造字段。不要为了得到 COMPLETE 跳过异常。
若想只比较同样输入的模型结果，也可以在新建 live 案件后，用第 2 节的 `$visaScenario.events[0].text` 和三份材料逐步走一次。

本文准备时原 `data/` 的请求账本为 **32/60**，剩余 28 次；后续调用会继续累计。每事件最多四次请求。不要通过重新建存储目录绕过本次预算。切换 mode 不会重新处理已经完成的同 ID 事件，因此对比时应创建新案件。

## 7. 看到问题时查哪里

```powershell
& $visa @visaArgs inspect $visaCaseId
& $visa @visaArgs events $visaCaseId
& $visa @visaArgs trace $visaCaseId
```

- `inspect`：当前 facts、documents、checks、版本和审批。
- `events`：输入是否 pending/failed/done，是否可以重试。
- `trace`：run_id、原文/OCR、模型候选字段、拒绝理由、工具调用、状态前后差异和用量。

需要保存供排查时：

```powershell
New-Item -ItemType Directory -Force 'output/manual' | Out-Null
& $visa @visaArgs trace $visaCaseId | Out-File "output/manual/$visaCaseId-trace.json" -Encoding UTF8
```

告诉我案件 ID、你发了什么、期望什么、实际出现什么即可。你也可以在 VS Code 打开 `src/visa_agent/service.py` 看单轮执行、`rules.py` 看业务判断、`evidence.py` 看字段为什么被拒绝。
