from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_container_files_and_release_version_exist() -> None:
    assert (ROOT / "Dockerfile").is_file()
    assert (ROOT / ".dockerignore").is_file()
    assert (ROOT / "docker-compose.yml").is_file()
    assert (ROOT / "docker/entrypoint.sh").is_file()
    assert (ROOT / "docker/healthcheck.sh").is_file()
    assert 'version = "1.0.0"' in (ROOT / "pyproject.toml").read_text()
    assert "1.0.0" in (ROOT / "CHANGELOG.md").read_text()


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
    assert "docker.sock" not in compose and "privileged" not in compose


def test_container_sources_do_not_contain_secret_literals() -> None:
    paths = [ROOT / "Dockerfile", ROOT / ".dockerignore", ROOT / "docker-compose.yml"]
    content = "\n".join(path.read_text() for path in paths)
    assert "sk-" not in content
    assert "BEGIN PRIVATE KEY" not in content
    assert "your-key" not in content
