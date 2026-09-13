import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
CURRENT_VERSION = "1.0.3"


def test_container_files_and_release_version_exist() -> None:
    assert (ROOT / "Dockerfile").is_file()
    assert (ROOT / ".dockerignore").is_file()
    assert (ROOT / "docker-compose.yml").is_file()
    assert (ROOT / "docker/entrypoint.sh").is_file()
    assert (ROOT / "docker/healthcheck.sh").is_file()
    assert f'version = "{CURRENT_VERSION}"' in (ROOT / "pyproject.toml").read_text()
    assert f"## {CURRENT_VERSION} " in (ROOT / "CHANGELOG.md").read_text()
    assert (
        f'__version__ = "{CURRENT_VERSION}"' in (ROOT / "src/ninja_agent/__init__.py").read_text()
    )
    assert f"VERSION ?= {CURRENT_VERSION}" in (ROOT / "Makefile").read_text()
    assert f"ninja-mcp:local-{CURRENT_VERSION}" in (ROOT / "docker-compose.yml").read_text()


def test_release_workflow_uses_token_authentication_without_oidc() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    assert "PYPI_API_TOKEN" in workflow
    assert "user: __token__" in workflow
    assert "password: ${{ secrets.PYPI_API_TOKEN }}" in workflow
    assert "id-token: write" not in workflow
    assert "PYPI_API_TOKEN is required" in workflow


def test_container_configuration_has_safe_runtime_defaults() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    compose = (ROOT / "docker-compose.yml").read_text()
    ignore = (ROOT / ".dockerignore").read_text()

    assert "python:3.12-slim" in dockerfile
    assert "useradd" in dockerfile and "USER ninja" in dockerfile
    assert "pip install" in dockerfile and "[coder,researcher,secretary,agent]" in dockerfile
    assert "ENTRYPOINT" in dockerfile
    assert all(item in ignore for item in (".env", "credentials", ".git", ".cache"))
    assert all(
        f"profiles: [{name}]" in compose for name in ("coder", "researcher", "secretary", "agent")
    )
    assert all(port in compose for port in ("8100", "8101", "8102", "8103"))
    assert "127.0.0.1:" in compose
    assert compose.count("healthcheck:") == 4
    assert "ninja-config:" in compose and "ninja-cache:" in compose
    assert "ninja-published" in compose
    assert "docker.sock" not in compose and "privileged" not in compose


def test_container_sources_do_not_contain_secret_literals() -> None:
    paths = [ROOT / "Dockerfile", ROOT / ".dockerignore", ROOT / "docker-compose.yml"]
    content = "\n".join(path.read_text() for path in paths)
    assert "sk-" not in content
    assert "BEGIN PRIVATE KEY" not in content
    assert "your-key" not in content


def test_makefile_exposes_safe_release_and_quality_targets() -> None:
    makefile = (ROOT / "Makefile").read_text()
    for target in (
        "help",
        "install",
        "install-native",
        "install-headless",
        "docker-build",
        "docker-config",
        "docker-up",
        "docker-down",
        "docker-status",
        "docker-logs",
        "docker-clean",
        "test",
        "test-docker",
        "lint",
        "format-check",
        "typecheck",
        "check",
        "version",
        "package",
        "release-check",
    ):
        assert f"{target}:" in makefile
    assert ".DEFAULT_GOAL := help" in makefile
    assert ".PHONY:" in makefile
    assert "NINJA_DOCKER_NONINTERACTIVE=1 ./install.sh" in makefile
    assert "--volumes --remove-orphans" in makefile


def test_make_help_lists_categories_and_examples() -> None:
    result = subprocess.run(
        ["make", "help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Installation:" in result.stdout
    assert "Docker (requires a TUI-generated config):" in result.stdout
    assert "make docker-up PROFILE=coder" in result.stdout
    assert "Quality and release:" in result.stdout
