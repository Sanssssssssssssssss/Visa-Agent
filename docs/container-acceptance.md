# Container acceptance / 容器验收

2026-10-07：Linux amd64 的 runtime/test 镜像实际构建运行通过，容器内 **250 passed**，本机及 Windows/Linux 原生 CI 通过。[容器 CI](https://github.com/Sanssssssssssssssss/Visa-Agent/actions/runs/37533230312) · [原生 CI](https://github.com/Sanssssssssssssssss/Visa-Agent/actions/runs/37533230372) · [镜像 ID 与机器记录](validation/container.json)。验证代码版本 `f287706`。

The first run built both images but failed acceptance: frozen replays require explicit review mode, and the optional local test UI assumed an editable source path. Its smoke command also passed through a pipe without propagating the failing exit code. These were corrected; the pipeline now parses the acceptance JSON and stops on any failure. The original failed run is retained at [37531396397](https://github.com/Sanssssssssssssssss/Visa-Agent/actions/runs/37531396397).

| 检查 | 实际结果 |
|---|---|
| 普通用户与只读运行 | UID 10001，根文件系统只读 |
| 文档处理 | JPG、扫描 PDF 真正经过 OCR；未使用预置文本替代 |
| 三路线 | 每条分别完成有复核/无复核的离线 ZIP，文件校验通过 |
| 启动与恢复 | 首次初始化、再次启动保留扫描起点、备份恢复保留案件 |
| 停机与健康 | 实际 SIGTERM 正常退出、锁释放；本地健康检查通过 |
| Compose 运维 | Secrets 挂载、named volume、重启后案件及配置哈希一致 |
| 隐私与测试 | 镜像无本机 .env/客户配置；test 镜像内 250 项通过 |

No container test uses a real model key, QQ account or outbound email. Model and live-mail evidence remains in the separate recorded acceptance reports.

Compose 验证仅在 CI 显式挂载假邮箱传输，运行生产入口、文件卷和启停流程；没有把 fake transport 加成产品运行模式。当前 Windows 收件后台保持独立运行，未用同一真实邮箱启动第二个 worker。容器的新真实邮箱登录由部署者配置后用 `probe` 验证。Windows 绝对路径自动迁移到 Linux、arm64、真实 systemd 主机及 GHCR 发布未在本次验收中执行。
