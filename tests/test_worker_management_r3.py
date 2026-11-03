"""Unit tests for R3.2 worker start/stop/status management."""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

from scripts.manage_research_worker import (
    PID_FILE,
    _is_running,
    _read_pid,
    cmd_status,
    cmd_stop,
)


def test_status_no_pid_file(tmp_path):
    with patch("scripts.manage_research_worker.PID_FILE", tmp_path / "nonexistent.pid"):
        assert cmd_status() == 0


def test_status_stale_pid(tmp_path):
    pid_file = tmp_path / "worker.pid"
    pid_file.write_text("999999")
    with patch("scripts.manage_research_worker.PID_FILE", pid_file):
        assert cmd_status() == 0  # stale → stopped


def test_stop_no_pid_file(tmp_path):
    with patch("scripts.manage_research_worker.PID_FILE", tmp_path / "nonexistent.pid"):
        assert cmd_stop() == 1  # nothing to stop


def test_stop_stale_pid_cleans_up(tmp_path):
    pid_file = tmp_path / "worker.pid"
    pid_file.write_text("999999")
    with patch("scripts.manage_research_worker.PID_FILE", pid_file):
        assert cmd_stop() == 0
        assert not pid_file.exists()


def test_pid_file_path_is_under_workbuddy():
    assert ".workbuddy" in str(PID_FILE)
    assert PID_FILE.name == "research-worker.pid"


def test_is_running_returns_false_for_dead_pid():
    # PID 999999 is extremely unlikely to exist.
    assert _is_running(999999) is False
