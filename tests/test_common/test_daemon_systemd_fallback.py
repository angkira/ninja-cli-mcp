"""Tests for systemd-aware DaemonManager.status fallback."""

from __future__ import annotations

from ninja_common.daemon import DaemonManager


def _make_manager(tmp_path):
    return DaemonManager(cache_dir=tmp_path / ".cache" / "ninja-mcp")


def test_status_falls_back_to_systemd_owner(tmp_path, monkeypatch):
    dm = _make_manager(tmp_path)
    monkeypatch.setattr(dm, "_read_pid", lambda module: None)
    monkeypatch.setattr(dm, "_get_port", lambda module: 8100)
    monkeypatch.setattr(dm, "_is_port_in_use", lambda port: True)
    monkeypatch.setattr(dm, "_find_ninja_owner_pid", lambda module, port: 4242)
    monkeypatch.setattr(dm, "_is_systemd_active", lambda module: True)

    status = dm.status("coder")
    assert status["running"] is True
    assert status["pid"] == 4242
    assert status["url"] == "http://127.0.0.1:8100/sse"
    assert status["source"] == "systemd"


def test_status_falls_back_to_port_owner_without_systemd(tmp_path, monkeypatch):
    dm = _make_manager(tmp_path)
    monkeypatch.setattr(dm, "_read_pid", lambda module: None)
    monkeypatch.setattr(dm, "_get_port", lambda module: 8100)
    monkeypatch.setattr(dm, "_is_port_in_use", lambda port: True)
    monkeypatch.setattr(dm, "_find_ninja_owner_pid", lambda module, port: 4243)
    monkeypatch.setattr(dm, "_is_systemd_active", lambda module: False)

    status = dm.status("coder")
    assert status["running"] is True
    assert status["pid"] == 4243
    assert status["source"] == "port"


def test_status_not_running_when_port_free(tmp_path, monkeypatch):
    dm = _make_manager(tmp_path)
    monkeypatch.setattr(dm, "_read_pid", lambda module: None)
    monkeypatch.setattr(dm, "_get_port", lambda module: 8100)
    monkeypatch.setattr(dm, "_is_port_in_use", lambda port: False)

    status = dm.status("coder")
    assert status["running"] is False
    assert status["pid"] is None


def test_status_prefers_pid_file_when_live(tmp_path, monkeypatch):
    dm = _make_manager(tmp_path)
    monkeypatch.setattr(dm, "_read_pid", lambda module: 1111)
    monkeypatch.setattr(dm, "_is_running", lambda pid: True)
    monkeypatch.setattr(dm, "_get_port", lambda module: 8100)

    status = dm.status("coder")
    assert status["running"] is True
    assert status["pid"] == 1111
    assert status["source"] == "pid"


def test_is_systemd_active_false_without_systemctl(monkeypatch):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        dm = DaemonManager(cache_dir=Path(tmp))
        monkeypatch.setattr("shutil.which", lambda name: None)
        # Force FileNotFoundError from subprocess.run
        import subprocess

        def _raise(*a, **k):
            raise FileNotFoundError("no systemctl")

        monkeypatch.setattr(subprocess, "run", _raise)
        assert dm._is_systemd_active("coder") is False


def test_find_ninja_owner_skips_connected_clients(tmp_path, monkeypatch):
    """lsof lists clients too — the owner must be the ninja server PID."""
    import psutil

    dm = _make_manager(tmp_path)
    monkeypatch.setattr(dm, "_find_pids_using_port", lambda port: [111, 222, 333])

    class _FakeProc:
        def __init__(self, pid):
            self._pid = pid

        def cmdline(self):
            if self._pid == 333:
                return ["/usr/bin/python3", "-m", "ninja_coder.server", "--http"]
            return ["claude", "--permission-mode=bypassPermissions"]

    monkeypatch.setattr(psutil, "Process", _FakeProc)
    assert dm._find_ninja_owner_pid("coder", 8100) == 333


def test_find_ninja_owner_none_when_no_server(tmp_path, monkeypatch):
    import psutil

    dm = _make_manager(tmp_path)
    monkeypatch.setattr(dm, "_find_pids_using_port", lambda port: [111, 222])

    class _FakeProc:
        def cmdline(self):
            return ["claude"]

    monkeypatch.setattr(psutil, "Process", lambda pid: _FakeProc())
    assert dm._find_ninja_owner_pid("coder", 8100) is None
