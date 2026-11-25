"""Tests for systemd-aware daemon restart/stop and honest version reporting.

Everything is mocked: no real systemd units, no real processes, no network.
The exact ``systemctl`` argv is asserted so the unit scope can never drift.
"""

from __future__ import annotations

import logging
import subprocess
from types import SimpleNamespace

from ninja_common.daemon import DaemonManager


UNIT = "ninja-mcp@coder.service"


class FakeSystemctl:
    """Stand-in for ``systemctl --user`` with live-process bookkeeping."""

    def __init__(
        self,
        *,
        active: bool = True,
        main_pid: int = 1000,
        new_pid: int = 2000,
        ignore_restart: bool = False,
        ignore_stop: bool = False,
    ):
        self.calls: list[list[str]] = []
        self.active = active
        self.main_pid = main_pid
        self.new_pid = new_pid
        self.ignore_restart = ignore_restart
        self.ignore_stop = ignore_stop
        self.restarted = False
        self.port_up = False
        self.live_pids: set[int] = {main_pid} if active else set()

    # ── subprocess.run replacement ──────────────────────────────────────────
    def run(self, argv: list[str], **kwargs: object) -> SimpleNamespace:
        assert kwargs.get("capture_output") is True
        assert kwargs.get("text") is True
        assert kwargs.get("timeout") is not None
        assert not kwargs.get("shell")
        self.calls.append(list(argv))

        assert argv[0] == "systemctl"
        assert argv[1] == "--user", f"scope must always be --user: {argv}"
        verb = argv[2]

        if verb == "is-active":
            return self._result(0 if self.active else 3, "active\n" if self.active else "inactive\n")

        if verb == "show":
            prop = argv[argv.index("-p") + 1]
            if prop == "MainPID":
                return self._result(0, f"{self.main_pid if self.active else 0}\n")
            if prop == "ActiveEnterTimestamp":
                return self._result(0, "1700000000\n")
            raise AssertionError(f"unexpected property: {prop}")

        if verb == "restart":
            if not self.ignore_restart:
                self.restarted = True
                self.main_pid = self.new_pid
                self.live_pids = {self.new_pid}
                self.port_up = True
            return self._result(0, "")

        if verb == "stop":
            if not self.ignore_stop:
                self.active = False
                self.main_pid = 0
                self.live_pids = set()
                self.port_up = False
            return self._result(0, "")

        raise AssertionError(f"unexpected systemctl verb: {argv}")

    # ── DaemonManager hooks ─────────────────────────────────────────────────
    def is_running(self, pid: int) -> bool:
        return pid in self.live_pids

    def is_port_in_use(self, port: int) -> bool:
        return self.port_up

    @staticmethod
    def _result(returncode: int, stdout: str) -> SimpleNamespace:
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def _make_manager(tmp_path) -> DaemonManager:
    dm = DaemonManager(cache_dir=tmp_path / ".cache" / "ninja-mcp")
    dm.systemd_restart_timeout = 0.05
    dm.systemd_stop_timeout = 0.05
    dm.port_ready_timeout = 0.05
    dm.poll_interval = 0.005
    return dm


def _wire(monkeypatch, dm: DaemonManager, fake: FakeSystemctl) -> None:
    monkeypatch.setattr(subprocess, "run", fake.run)
    monkeypatch.setattr(dm, "_is_running", fake.is_running)
    monkeypatch.setattr(dm, "_is_port_in_use", fake.is_port_in_use)
    monkeypatch.setattr(dm, "_get_port", lambda module: 8100)


def _assert_unit_scoped(calls: list[list[str]]) -> None:
    """Every systemctl call must be --user scoped and name only our unit."""
    for argv in calls:
        assert argv[0] == "systemctl"
        assert argv[1] == "--user"
        assert "--all" not in argv
        assert argv[-1] == UNIT


def test_systemd_restart_observes_new_main_pid(tmp_path, monkeypatch):
    dm = _make_manager(tmp_path)
    fake = FakeSystemctl(main_pid=1000, new_pid=2000)
    _wire(monkeypatch, dm, fake)

    assert dm.restart("coder") is True
    assert fake.restarted is True
    _assert_unit_scoped(fake.calls)

    restart_calls = [argv for argv in fake.calls if argv[2] == "restart"]
    assert restart_calls == [["systemctl", "--user", "restart", UNIT]]

    # MainPID was read before (ownership) and after (verification).
    pid_reads = [argv for argv in fake.calls if argv[2] == "show" and "MainPID" in argv]
    assert len(pid_reads) >= 2
    assert pid_reads[-1] == ["systemctl", "--user", "show", "-p", "MainPID", "--value", UNIT]


def test_systemd_restart_fails_when_main_pid_never_changes(tmp_path, monkeypatch, caplog):
    dm = _make_manager(tmp_path)
    fake = FakeSystemctl(main_pid=1000, ignore_restart=True)
    _wire(monkeypatch, dm, fake)

    with caplog.at_level(logging.ERROR):
        assert dm.restart("coder") is False

    assert fake.restarted is False
    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    assert any("coder" in message and "NOT restarted" in message for message in errors)


def test_systemd_restart_fails_when_port_does_not_answer(tmp_path, monkeypatch, caplog):
    dm = _make_manager(tmp_path)
    fake = FakeSystemctl(main_pid=1000, new_pid=2000)
    _wire(monkeypatch, dm, fake)
    # PID changes but the module never starts listening.
    monkeypatch.setattr(dm, "_wait_for_port", lambda module, timeout, interval: False)

    with caplog.at_level(logging.ERROR):
        assert dm.restart("coder") is False

    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    assert any("not answering" in message for message in errors)


def test_stop_stops_systemd_unit_instead_of_silent_noop(tmp_path, monkeypatch):
    dm = _make_manager(tmp_path)
    fake = FakeSystemctl(active=True, main_pid=1000)
    _wire(monkeypatch, dm, fake)

    assert dm.stop("coder") is True
    stop_calls = [argv for argv in fake.calls if argv[2] == "stop"]
    assert stop_calls == [["systemctl", "--user", "stop", UNIT]]
    _assert_unit_scoped(fake.calls)


def test_stop_reports_failure_when_unit_stays_active(tmp_path, monkeypatch, caplog):
    dm = _make_manager(tmp_path)
    fake = FakeSystemctl(active=True, main_pid=1000, ignore_stop=True)
    _wire(monkeypatch, dm, fake)

    with caplog.at_level(logging.ERROR):
        assert dm.stop("coder") is False

    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    assert any("coder" in message and "still active" in message for message in errors)


def test_pidfile_module_uses_legacy_path_without_systemctl(tmp_path, monkeypatch):
    dm = _make_manager(tmp_path)
    dm._get_pid_file("coder").write_text("4242")

    fake = FakeSystemctl(active=False)
    _wire(monkeypatch, dm, fake)

    alive = {"value": True}

    def fake_kill(pid: int, sig: int) -> None:
        assert pid == 4242
        alive["value"] = False

    monkeypatch.setattr("ninja_common.daemon.os.kill", fake_kill)
    monkeypatch.setattr(dm, "_is_running", lambda pid: alive["value"])

    started: list[str] = []
    monkeypatch.setattr(dm, "start", lambda module: started.append(module) or True)

    assert dm.restart("coder") is True
    assert started == ["coder"]
    # Legacy path must not touch systemd at all.
    assert fake.calls == []


def test_status_stale_code_true_when_daemon_predates_install(tmp_path, monkeypatch):
    dm = _make_manager(tmp_path)
    monkeypatch.setattr(dm, "_read_pid", lambda module: 1234)
    monkeypatch.setattr(dm, "_is_running", lambda pid: True)
    monkeypatch.setattr(dm, "_get_port", lambda module: 8100)
    monkeypatch.setattr(dm, "_installed_version", lambda: "2.0.0")
    monkeypatch.setattr(dm, "_install_mtime", lambda: 2000.0)
    monkeypatch.setattr(dm, "_process_start_time", lambda module, pid, source: 1000.0)

    status = dm.status("coder")
    assert status["installed_version"] == "2.0.0"
    assert status["running_since"] is not None
    assert status["stale_code"] is True
    assert "version" not in status


def test_status_stale_code_false_when_daemon_postdates_install(tmp_path, monkeypatch):
    dm = _make_manager(tmp_path)
    monkeypatch.setattr(dm, "_read_pid", lambda module: 1234)
    monkeypatch.setattr(dm, "_is_running", lambda pid: True)
    monkeypatch.setattr(dm, "_get_port", lambda module: 8100)
    monkeypatch.setattr(dm, "_installed_version", lambda: "2.0.0")
    monkeypatch.setattr(dm, "_install_mtime", lambda: 2000.0)
    monkeypatch.setattr(dm, "_process_start_time", lambda module, pid, source: 3000.0)

    status = dm.status("coder")
    assert status["stale_code"] is False


def test_is_stale_code_requires_both_timestamps(tmp_path):
    dm = _make_manager(tmp_path)
    assert dm._is_stale_code(1000.0, 2000.0) is True
    assert dm._is_stale_code(3000.0, 2000.0) is False
    assert dm._is_stale_code(None, 2000.0) is None
    assert dm._is_stale_code(1000.0, None) is None
