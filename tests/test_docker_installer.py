from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from ninja_config.docker_installer import DockerSetupConfig, validate_port, validate_workspace


ROOT = Path(__file__).parents[1]


def test_public_help_hides_docker_backend_flags() -> None:
    result = subprocess.run(
        [str(ROOT / "install.sh"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--docker" not in result.stdout
    assert "NINJA_DOCKER" not in result.stdout


def test_removed_docker_flag_is_rejected_without_starting_docker(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_marker = tmp_path / "docker-started"
    (fake_bin / "docker").write_text(f"#!/bin/sh\ntouch '{docker_marker}'\nexit 0\n")
    (fake_bin / "docker").chmod(0o755)
    result = subprocess.run(
        [str(ROOT / "install.sh"), "--docker"],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "Unknown argument: --docker" in result.stderr
    assert not docker_marker.exists()


def _run_installer(tmp_path: Path, **settings: str) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text("#!/bin/sh\nexit 0\n")
    (fake_bin / "docker").chmod(0o755)
    env = os.environ.copy()
    env.update(settings)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["HOME"] = str(tmp_path / "home")
    env["NINJA_DOCKER_CONFIG_DIR"] = str(tmp_path / "docker-config")
    env["NINJA_DOCKER_NONINTERACTIVE"] = "1"
    return subprocess.run(
        [str(ROOT / "install.sh")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_docker_installer_generates_non_secret_config_and_wrapper(tmp_path: Path) -> None:
    result = _run_installer(
        tmp_path,
        NINJA_DOCKER_WORKSPACE=str(ROOT),
        NINJA_DOCKER_PROFILES="coder,agent",
        NINJA_DOCKER_CODER_PORT="18100",
        NINJA_DOCKER_AGENT_PORT="18103",
        OPENROUTER_API_KEY="sk-test-must-not-be-written",
    )
    assert result.returncode == 0, result.stderr
    config_dir = tmp_path / "docker-config"
    config = (config_dir / ".env").read_text()
    assert "sk-test-must-not-be-written" not in config
    assert "NINJA_DOCKER_PROFILES=coder,agent" in config
    assert (config_dir / "ninja-mcp-docker").is_file()
    wrapper = (config_dir / "ninja-mcp-docker").read_text()
    assert "docker.sock" not in wrapper
    assert '--env-file "$NINJA_DOCKER_RUNTIME_ENV_FILE"' in wrapper
    assert ".env" in (ROOT / ".dockerignore").read_text()


def test_docker_wrapper_stop_uses_selected_profiles(tmp_path: Path) -> None:
    result = _run_installer(
        tmp_path,
        NINJA_DOCKER_WORKSPACE=str(ROOT),
        NINJA_DOCKER_PROFILES="coder,agent",
    )
    assert result.returncode == 0, result.stderr
    fake_docker = tmp_path / "bin" / "docker"
    args_log = tmp_path / "docker-args.log"
    fake_docker.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{args_log}"\n')
    fake_docker.chmod(0o755)
    wrapper_result = subprocess.run(
        [str(tmp_path / "docker-config" / "ninja-mcp-docker"), "stop"],
        env={**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert wrapper_result.returncode == 0, wrapper_result.stderr
    docker_args = args_log.read_text().splitlines()
    project_name_index = docker_args.index("--project-name")
    assert docker_args[project_name_index - 1] == "compose"
    assert docker_args[project_name_index + 1] == "ninja-mcp"
    assert docker_args[project_name_index + 2] == "--env-file"
    assert docker_args[docker_args.index("--profile") + 1] == "coder"
    assert (
        docker_args[docker_args.index("--profile", docker_args.index("--profile") + 1) + 1]
        == "agent"
    )
    assert docker_args[-1] == "down"
    wrapper = (tmp_path / "docker-config" / "ninja-mcp-docker").read_text()
    assert "profile_args=()" in wrapper
    assert 'stop) shift; compose "${profile_args[@]}" down "$@"' in wrapper


def test_generated_config_uses_active_profiles_and_publishes_configured_port(
    tmp_path: Path,
) -> None:
    result = _run_installer(
        tmp_path,
        NINJA_DOCKER_WORKSPACE=str(ROOT),
        NINJA_DOCKER_PROFILES="coder",
        NINJA_DOCKER_CODER_PORT="18100",
    )
    assert result.returncode == 0, result.stderr

    config_dir = tmp_path / "docker-config"
    wrapper = config_dir / "ninja-mcp-docker"
    compose = subprocess.run(
        [str(wrapper), "config"],
        env={**os.environ, "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )
    if "docker: command not found" in compose.stderr or "Docker Compose v2" in compose.stderr:
        pytest.skip("Docker Compose is not installed")
    assert compose.returncode == 0, compose.stderr
    assert 'published: "18100"' in compose.stdout
    assert "host_ip: 127.0.0.1" in compose.stdout
    assert "target: 8100" in compose.stdout

    args_log = tmp_path / "start-args.log"
    fake_docker = tmp_path / "start-bin" / "docker"
    fake_docker.parent.mkdir()
    fake_docker.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{args_log}"\n')
    fake_docker.chmod(0o755)
    start = subprocess.run(
        [str(wrapper), "start"],
        env={**os.environ, "PATH": f"{fake_docker.parent}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert start.returncode == 0, start.stderr
    start_args = args_log.read_text().splitlines()
    assert start_args[start_args.index("--project-name") + 1] == "ninja-mcp"
    assert start_args[start_args.index("--env-file") + 1] == str(config_dir / ".env")
    assert start_args[start_args.index("--profile") + 1] == "coder"
    assert start_args[-2:] == ["up", "-d"]

    wrapper_text = wrapper.read_text()
    assert 'args+=(--profile "$profile")' in wrapper_text
    assert 'config) compose "${profile_args[@]}" config' in wrapper_text
    assert 'start) shift; compose "${profile_args[@]}" up -d "$@"' in wrapper_text


def test_archive_fallback_accepts_nonstandard_directory() -> None:
    script = (ROOT / "install.sh").read_text()
    assert 'mv "$TEMP_DIR/ninja-cli-mcp-main" "$TEMP_DIR/ninja-mcp"' not in script
    assert 'for candidate in "$TEMP_DIR"/*' in script


def test_docker_installer_rejects_duplicate_ports_before_build(tmp_path: Path) -> None:
    result = _run_installer(
        tmp_path,
        NINJA_DOCKER_CODER_PORT="18100",
        NINJA_DOCKER_RESEARCHER_PORT="18100",
    )
    assert result.returncode != 0
    assert "must be unique" in result.stderr or "must be unique" in result.stdout


def test_typed_docker_config_validates_workspace_and_ports(tmp_path: Path) -> None:
    workspace = validate_workspace(tmp_path)
    config = DockerSetupConfig(workspace, ("coder", "agent"), {"coder": 18100, "agent": 18103})
    config.validate()
    assert validate_port("18100") == 18100


def test_typed_docker_config_rejects_invalid_workspace_and_duplicate_ports(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workspace"):
        validate_workspace(tmp_path / "missing")
    config = DockerSetupConfig(tmp_path, ("coder", "agent"), {"coder": 18100, "agent": 18100})
    with pytest.raises(ValueError, match="unique"):
        config.validate()
