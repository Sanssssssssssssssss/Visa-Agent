# Contributing / 贡献

Keep changes small and inspectable. A rule change should name its official source, applicable branch and verification date; a model change should preserve source validation and recorded failures.

1. Install with `uv sync --locked --python 3.12`.
2. Make a branch such as `codex/describe-the-change`.
3. Run the checks in [TESTING.md](TESTING.md). Add regression coverage when fixing a meaningful failure; avoid tests that only repeat implementation details.
4. Describe the changed behavior, evidence and remaining limits in the PR. Distinguish offline tests from model calls and real delivery.

Do not commit `.env`, mailbox configuration, OAuth caches, real applicants' files, raw mail, private traces or third-party reference PDFs without redistribution rights. Synthetic applicants must be labelled. [Data sources](docs/dataset.md).

代码优先使用明确函数和类型；增加规则时记录来源和适用条件，业务判断放在可读的检查函数。中英文用户措辞一起维护；失败不能转换成模拟成功。更新冻结数据需要建立新基线，保留旧失败的可追溯记录。

Documentation structure follows [docs/README.md](docs/README.md). Main README and operational guides have language links. Runtime and local operator details should not appear in customer replies.
