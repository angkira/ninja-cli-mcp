"""Interactive Docker setup and typed validation."""

from __future__ import annotations

import os
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from InquirerPy import inquirer
from InquirerPy.base.control import Choice


DEFAULT_PORTS = {"coder": 8100, "researcher": 8101, "secretary": 8102, "agent": 8103}
SUPPORTED_PROFILES = tuple(DEFAULT_PORTS)


@dataclass(frozen=True)
class DockerSetupConfig:
    workspace: Path
    profiles: tuple[str, ...]
    ports: dict[str, int]
    agent_read_only: bool = False
    build: bool = True
    start: bool = True
    runtime_env_file: Path | None = None

    def validate(self) -> None:
        if not self.workspace.exists() or not self.workspace.is_dir():
            raise ValueError("workspace must be an existing directory")
        if not self.profiles or any(p not in SUPPORTED_PROFILES for p in self.profiles):
            raise ValueError("at least one supported Docker profile is required")
        values = [self.ports[p] for p in self.profiles]
        if len(values) != len(set(values)):
            raise ValueError("Docker host ports must be unique")
        if any(not 1024 <= port <= 65535 for port in values):
            raise ValueError("Docker host ports must be between 1024 and 65535")


def validate_workspace(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise ValueError("workspace must be an existing directory")
    return path


def validate_port(value: str | int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("port must be a number from 1024 to 65535") from exc
    if not 1024 <= port <= 65535:
        raise ValueError("port must be a number from 1024 to 65535")
    return port


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.1)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _exec(result: Any) -> Any:
    return result.execute() if hasattr(result, "execute") else result


def _text(message: str, default: str) -> str:
    return str(_exec(inquirer.text(message=message, default=default))).strip()


def collect_docker_setup() -> DockerSetupConfig:
    workspace = validate_workspace(_text("Workspace path:", str(Path.cwd())))
    profiles = (
        _exec(
            inquirer.checkbox(
                message="Services to run:",
                choices=[
                    Choice(value=p, name=p.title(), enabled=p == "coder")
                    for p in SUPPORTED_PROFILES
                ],
                instruction="Select at least one service",
            )
        )
        or []
    )
    if not profiles:
        raise ValueError("select at least one Docker service")
    ports: dict[str, int] = {}
    for profile in profiles:
        while True:
            try:
                port = validate_port(
                    _text(f"Host port for {profile}:", str(DEFAULT_PORTS[profile]))
                )
                if port in ports.values():
                    raise ValueError("Docker host ports must be unique")
                if not port_available(port):
                    print(f"  Warning: localhost port {port} appears occupied.")
                ports[profile] = port
                break
            except ValueError as exc:
                print(f"  Invalid port: {exc}; please try again.")
    agent_read_only = False
    if "agent" in profiles:
        agent_read_only = (
            _exec(inquirer.confirm(message="Give agent write access to workspace?", default=True))
            is not True
        )
    build = _exec(inquirer.confirm(message="Build the image now?", default=True)) is True
    start = _exec(inquirer.confirm(message="Start selected containers now?", default=True)) is True
    runtime_env_file = None
    print("  Host-authenticated CLIs are not available inside the container.")
    if (
        _exec(inquirer.confirm(message="Pass API keys to containers for this run?", default=False))
        is True
    ):
        keys = (
            _exec(
                inquirer.checkbox(
                    message="Providers to pass:",
                    choices=[
                        Choice(value=k, name=k)
                        for k in (
                            "OPENROUTER_API_KEY",
                            "SERPER_API_KEY",
                            "PERPLEXITY_API_KEY",
                            "GOOGLE_API_KEY",
                        )
                    ],
                )
            )
            or []
        )
        for key in keys:
            value = _exec(inquirer.secret(message=f"{key} (Enter to skip):"))
            if value:
                os.environ[key] = str(value)
        if (
            _exec(
                inquirer.confirm(message="Persist credentials in a protected file?", default=False)
            )
            is True
        ):
            runtime_env_file = Path.home() / ".config/ninja-mcp/docker/runtime.env"
    config = DockerSetupConfig(
        validate_workspace(workspace),
        tuple(profiles),
        ports,
        agent_read_only,
        build,
        start,
        runtime_env_file,
    )
    config.validate()
    return config


def run_docker_setup(config: DockerSetupConfig, source_dir: Path | None = None) -> int:
    """Call the existing shell backend with values collected by the TUI."""
    config.validate()
    source = source_dir or Path(os.environ.get("NINJA_DOCKER_SOURCE_DIR", Path.cwd()))
    if not (source / "install.sh").is_file():
        source = Path(__file__).resolve().parents[2]
    checkout: tempfile.TemporaryDirectory[str] | None = None
    if not (source / "install.sh").is_file():
        checkout = tempfile.TemporaryDirectory(prefix="ninja-mcp-docker-")
        source = Path(checkout.name) / "source"
        repo_url = os.environ.get("NINJA_REPO_URL", "https://github.com/angkira/ninja-cli-mcp.git")
        cloned = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(source)],
            capture_output=True,
            text=True,
            check=False,
        )
        if cloned.returncode != 0:
            checkout.cleanup()
            raise FileNotFoundError("Docker source bundle could not be downloaded")
    config_dir = Path(
        os.environ.get("NINJA_DOCKER_CONFIG_DIR", Path.home() / ".config/ninja-mcp/docker")
    )
    env = os.environ.copy()
    env.update(
        {
            "NINJA_DOCKER_WORKSPACE": str(config.workspace),
            "NINJA_DOCKER_PROFILES": ",".join(config.profiles),
            "NINJA_DOCKER_CONFIG_DIR": str(config_dir),
            "NINJA_DOCKER_START": "1" if config.start else "0",
            "NINJA_DOCKER_BUILD": "1" if config.build else "0",
            "NINJA_DOCKER_AGENT_ACCESS": "ro" if config.agent_read_only else "rw",
        }
    )
    for profile, port in config.ports.items():
        env[f"NINJA_DOCKER_{profile.upper()}_PORT"] = str(port)
    if config.runtime_env_file:
        config.runtime_env_file.parent.mkdir(parents=True, exist_ok=True)
        with config.runtime_env_file.open("w", encoding="utf-8") as handle:
            for key in (
                "OPENROUTER_API_KEY",
                "SERPER_API_KEY",
                "PERPLEXITY_API_KEY",
                "GOOGLE_API_KEY",
            ):
                if env.get(key):
                    handle.write(f"{key}={env[key]}\n")
        config.runtime_env_file.chmod(0o600)
        env["NINJA_DOCKER_RUNTIME_ENV_FILE"] = str(config.runtime_env_file)
    env["NINJA_DOCKER_NONINTERACTIVE"] = "1"
    result = subprocess.run(
        [str(source / "install.sh")],
        cwd=source,
        env=env,
        check=False,
    )
    if checkout is not None:
        checkout.cleanup()
    return result.returncode


def run_docker_tui(source_dir: Path | None = None) -> int:
    return run_docker_setup(collect_docker_setup(), source_dir)


if __name__ == "__main__":
    raise SystemExit(run_docker_tui())
