"""Tests for ninja-mcp CLI dispatch (ninja_common.ninja_cli)."""

from __future__ import annotations

import sys

import pytest

from ninja_common import ninja_cli


def test_update_delegates_to_update_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ninja-mcp update` calls ninja_common.update_cli.main()."""
    called: list[tuple[str, str]] = []
    real_delegate = ninja_cli._delegate

    def fake_delegate(module_path: str, command: str) -> None:
        called.append((module_path, command))
        if module_path == "ninja_common.update_cli":
            # Simulate the delegated main() exiting with a code.
            raise SystemExit(0)
        real_delegate(module_path, command)

    monkeypatch.setattr(ninja_cli, "_delegate", fake_delegate)
    monkeypatch.setattr(sys, "argv", ["ninja-mcp", "update", "--force"])

    with pytest.raises(SystemExit) as exc:
        ninja_cli.main()

    assert exc.value.code == 0
    assert called == [("ninja_common.update_cli", "update")]
