"""Guard against import-time environment mutation in the MCP server modules.

Importing ``ninja_*.server`` used to run ``ConfigManager().export_env()`` and
copy the developer's ``~/.ninja-mcp.env`` into ``os.environ`` for the whole
process. That made unrelated tests order dependent (they saw the developer's
``NINJA_MODEL``, ``NINJA_CODER_OPENCODE_PROVIDER``, ...).

Config export must happen only when a server is actually started (``run()``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


SERVER_MODULES = [
    "ninja_coder.server",
    "ninja_researcher.server",
    "ninja_secretary.server",
    "ninja_agent.server",
]

SRC_DIR = Path(__file__).resolve().parents[2] / "src"

# Canary keys that ``export_env()`` would inject if it ran at import time.
CANARY_CONFIG = """\
NINJA_MODEL=env-leak-canary
NINJA_CODER_MODEL=env-leak-canary-coder
NINJA_CODER_OPENCODE_PROVIDER=env-leak-canary-provider
NINJA_OPENCODE_TIMEOUT=987654
"""

_PROBE = textwrap.dedent(
    """
    import json
    import os
    import sys

    sys.path.insert(0, sys.argv[1])
    before = dict(os.environ)
    __import__(sys.argv[2])
    after = dict(os.environ)

    delta = {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
    }
    print("PROBE_DELTA:" + json.dumps(delta))
    """
)


def _probe_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """Build a HOME holding a config file whose values would leak if exported."""
    home = tmp_path / "home"
    home.mkdir()
    env_file = home / ".ninja-mcp.env"
    env_file.write_text(CANARY_CONFIG, encoding="utf-8")

    env = {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(SRC_DIR),
        "PYTHONNOUSERSITE": "1",
    }
    return env, env_file


@pytest.mark.parametrize("module", SERVER_MODULES)
def test_import_does_not_mutate_environ(module: str, tmp_path: Path) -> None:
    """Importing a server module must leave ``os.environ`` byte-identical."""
    env, env_file = _probe_environment(tmp_path)
    config_before = env_file.read_bytes()

    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, str(SRC_DIR), module],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert proc.returncode == 0, f"importing {module} failed:\n{proc.stderr}"
    markers = [line for line in proc.stdout.splitlines() if line.startswith("PROBE_DELTA:")]
    assert len(markers) == 1, f"probe produced no delta:\n{proc.stdout}\n{proc.stderr}"

    delta = json.loads(markers[0].removeprefix("PROBE_DELTA:"))
    assert delta == {"added": [], "removed": [], "changed": []}, (
        f"importing {module} mutated os.environ: {delta}"
    )

    # The import must not rewrite the config file either (ConfigManager()
    # also runs the secret migration).
    assert env_file.read_bytes() == config_before


@pytest.mark.parametrize("module", ["ninja_coder.server", "ninja_researcher.server"])
def test_run_exports_config_at_startup(module: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A real server start must still export config before serving."""
    import importlib
    import ninja_common.config_manager as config_manager_module

    server = importlib.import_module(module)

    exported: list[str] = []

    class RecordingConfigManager:
        def __init__(self, config_file: str | None = None) -> None:
            self.config_file = config_file

        def export_env(self) -> None:
            exported.append("export_env")

    monkeypatch.setattr(config_manager_module, "ConfigManager", RecordingConfigManager)
    monkeypatch.setattr(sys, "argv", [module, "--http", "--host", "127.0.0.1", "--port", "0"])

    async def fake_main_http(host: str, port: int) -> None:
        # Export must already have happened when the server starts serving.
        assert exported == ["export_env"], f"{module}.run() did not export config before startup"
        assert (host, port) == ("127.0.0.1", 0)

    monkeypatch.setattr(server, "main_http", fake_main_http)

    server.run()

    assert exported == ["export_env"]
