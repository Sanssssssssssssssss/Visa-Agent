# Container acceptance / 容器验收

Current validation is running in [container-checks](../.github/workflows/container.yml). Runtime/test images are built on a clean GitHub Ubuntu runner. The local Windows host has no Docker CLI; its live mail worker remains separate.

The first run built both images but failed acceptance: frozen replays require explicit review mode, and the optional local test UI assumed an editable source path. Its smoke command also passed through a pipe without propagating the failing exit code. These were corrected; the pipeline now parses the acceptance JSON and stops on any failure. The original failed run is retained at [37531396397](https://github.com/Sanssssssssssssssss/Visa-Agent/actions/runs/37531396397).

Required checks: non-root and read-only runtime; real OCR/image/scan decoding; three routes through reviewed and automatic offline ZIP delivery; case restoration; initialization that preserves scan start; health; graceful SIGTERM; no private configuration in the image; and the full test-image suite. Final results will be recorded here after the corrected run completes.

No container test uses a real model key, QQ account or outbound email. Model and live-mail evidence remains in the separate recorded acceptance reports.
