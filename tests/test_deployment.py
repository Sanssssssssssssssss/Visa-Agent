"""Test secret loading, first boot, safe backups and stop boundaries."""
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile

import pytest

from visa_agent.config import load_environment
from visa_agent.service import VisaService
from visa_agent.types import CaseEvent
from visa_agent.worker import mail_worker_lock

ROOT = Path(__file__).resolve().parents[1]
data_tools = runpy.run_path(str(ROOT / "scripts/manage_data.py"))


def test_secret_file_load_and_environment_priority(tmp_path, monkeypatch):
    secret = tmp_path / "key.txt"
    secret.write_text("test-file-key\n", encoding="utf-8-sig")
    monkeypatch.setenv("VISA_API_KEY_FILE", str(secret))
    monkeypatch.delenv("VISA_API_KEY", raising=False)
    load_environment()
    assert os.environ["VISA_API_KEY"] == "test-file-key"
    monkeypatch.setenv("VISA_API_KEY", "explicit-key")
    load_environment()
    assert os.environ["VISA_API_KEY"] == "explicit-key"
    monkeypatch.delenv("VISA_API_KEY", raising=False)
    secret.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_environment()


def test_container_setup_preserves_scan_start_on_second_boot(tmp_path, monkeypatch):
    monkeypatch.setenv("VISA_API_KEY", "test-model-key")
    monkeypatch.setenv("VISA_QQ_AUTH_CODE", "abcdefghijklmnop")
    monkeypatch.setenv("VISA_QQ_MAILBOX", "12345@qq.com")
    monkeypatch.setenv("VISA_QQ_ACCEPT_ALL", "1")
    monkeypatch.setenv("VISA_QQ_DATA_DIR", str(tmp_path))
    command = [sys.executable, str(ROOT / "scripts/container_entrypoint.py"), "setup"]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    before = (tmp_path / "qq-config.json").read_bytes()
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode == 0 and before == (tmp_path / "qq-config.json").read_bytes()
    assert b"abcdefghijklmnop" not in before and "test-model-key" not in first.stdout


def test_backup_restores_persisted_case_and_refuses_active_worker(tmp_path):
    data = tmp_path / "data"
    app = VisaService(data, "offline", hitl=False)
    app.create_case("c")
    app.handle_event(CaseEvent(case_id="c", event_id="e", text="route: visitor"))
    archive = tmp_path / "backup.tar.gz"
    with mail_worker_lock(data):
        with pytest.raises(ValueError, match="worker"):
            data_tools["backup"](data, archive)
    data_tools["backup"](data, archive)
    with pytest.raises(ValueError, match="empty"):
        data_tools["restore"](data, archive)
    data.rename(tmp_path / "preserved-data")
    data_tools["restore"](data, archive)
    restored = VisaService(data, "offline", hitl=False)
    assert restored.store.get("c").route == "visitor"
    assert len(restored.store.events("c")) == 1
    assert restored.handle_event(CaseEvent(case_id="c", event_id="e", text="route: visitor")).duplicate


def test_restore_rejects_traversal_before_writing(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as target:
        info = tarfile.TarInfo("../escaped.txt")
        info.size = 3
        target.addfile(info, io.BytesIO(b"bad"))
    with pytest.raises(ValueError, match="Unsafe"):
        data_tools["restore"](tmp_path / "data", archive)
    assert not (tmp_path / "escaped.txt").exists()
