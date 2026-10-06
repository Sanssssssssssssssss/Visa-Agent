"""Operational checks use real subprocess locks; model and mail calls stay offline."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from visa_agent.store import write_json
from visa_agent.worker import mail_worker_lock, worker_status


def test_worker_lock_rejects_second_process_and_recovers_after_exit(tmp_path):
    code = "from pathlib import Path; from visa_agent.worker import mail_worker_lock; import sys, os;\nwith mail_worker_lock(Path(sys.argv[1])): print('held', flush=True); sys.stdin.readline(); os._exit(1)"
    child = subprocess.Popen([sys.executable, "-c", code, str(tmp_path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        assert worker_status(tmp_path)["running"]
        with pytest.raises(ValueError, match="already owns"):
            with mail_worker_lock(tmp_path):
                pytest.fail("Second worker acquired the same inbox")
        with mail_worker_lock(tmp_path / "separate"):
            assert worker_status(tmp_path / "separate")["running"]
    finally:
        # Simulate an unexpected process exit; no stale PID should block restart.
        child.stdin.write("crash\n")
        child.stdin.flush()
        child.wait(timeout=10)
        child.stdin.close()
        child.stdout.close()
    assert not worker_status(tmp_path)["running"]
    with mail_worker_lock(tmp_path):
        assert worker_status(tmp_path)["running"]


def test_watch_recovers_after_repeated_network_failure_with_env_secret(tmp_path, monkeypatch):
    import visa_agent.qq_mail as module

    write_json(tmp_path / "qq-config.json", {"mailbox": "12345@qq.com", "accept_all": True})
    monkeypatch.setenv("VISA_QQ_AUTH_CODE", "test-only-secret")
    monkeypatch.setattr(module, "build_encrypted_persistence", lambda _: pytest.fail("Environment deployment must not require a desktop keyring"))
    calls, sleeps = [], []

    def receive(args, config, secret, budget):
        assert secret == "test-only-secret"
        calls.append(1)
        if len(calls) < 6:
            raise OSError("simulated provider outage")
        (tmp_path / "qq-stop").touch()
        return {"messages": [], "scanned": 0}

    monkeypatch.setattr(module, "receive_once", receive)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)
    monkeypatch.setattr(sys, "argv", ["qq_mail", "watch", "--data", str(tmp_path)])
    module.main()
    assert len(calls) == 6 and sleeps[:5] == [15, 30, 60, 60, 60]
    assert json.loads((tmp_path / "qq-watch-last.json").read_text())["scanned"] == 0
    assert not worker_status(tmp_path)["running"]


def test_status_needs_no_credentials_and_omits_customer_content(tmp_path, monkeypatch, capsys):
    import visa_agent.qq_mail as module

    write_json(tmp_path / "qq-watch-last.json", {"at": "2026-10-07T00:00:00+00:00", "messages": [{"reply": "private content"}]})
    monkeypatch.setattr(module, "build_encrypted_persistence", lambda _: pytest.fail("status must not read credentials"))
    monkeypatch.setattr(sys, "argv", ["qq_mail", "status", "--data", str(tmp_path)])
    module.main()
    assert "private content" not in capsys.readouterr().out


def test_headless_setup_preserves_config_and_keeps_secret_out_of_files(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/configure_qq.py"
    env = {**os.environ, "VISA_QQ_MAILBOX": "12345@qq.com", "VISA_QQ_AUTH_CODE": "abcdefghijklmnop"}
    args = [sys.executable, str(script), "--from-env", "--data", str(tmp_path), "--accept-all", "--allow-samples"]
    result = subprocess.run(args, env=env, capture_output=True)
    assert result.returncode == 0
    config = (tmp_path / "qq-config.json").read_bytes()
    assert json.loads(config)["allow_samples"] is True
    assert b"abcdefghijklmnop" not in config + result.stdout + result.stderr
    assert not (tmp_path / "qq-auth.bin").exists()
    assert subprocess.run(args, env=env, capture_output=True).returncode == 1
    assert (tmp_path / "qq-config.json").read_bytes() == config
