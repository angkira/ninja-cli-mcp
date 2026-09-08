# Container Quickstart

Ninja MCP 1.0.0 ships a Python 3.12 slim image. The image installs Ninja from
the local source tree plus the `coder`, `researcher`, `secretary`, and `agent`
extras. It runs as the non-root `ninja` user with `/workspace` as its working
directory.

## Build and one-shot commands

```bash
docker build -t ninja-mcp:1.0.0 .
docker run --rm -v "$PWD:/workspace:ro" ninja-mcp:1.0.0 \
  agent analyze --repo-root /workspace
```

With no arguments the image prints `ninja-mcp` help. Any arguments after the
image name are passed to `ninja-mcp`.

## SSE servers

Run one server directly, for example:

```bash
docker run --rm -p 127.0.0.1:8101:8101 \
  -e OPENROUTER_API_KEY \
  ninja-mcp:1.0.0 researcher --http --host 0.0.0.0 --port 8101
```

The SSE endpoints are `/sse` and `/messages`. Healthchecks probe `/sse`; the
project does not require a special `/health` endpoint.

## Compose profiles

Compose defines no default services, so credentials or ports are not consumed
unexpectedly. Build and start only what is needed:

```bash
docker compose --profile researcher up --build
docker compose --profile coder up --build
docker compose --profile secretary up --build
docker compose --profile agent run --rm agent analyze --repo-root /workspace
```

Ports bind to `127.0.0.1` by default. Services share an internal-only
`ninja` network. The workspace is `${NINJA_WORKSPACE:-.}`; coder and agent have
read-write access, while researcher and secretary use read-only mounts.

Named volumes preserve `/home/ninja/.ninja` and
`/home/ninja/.cache/ninja-mcp`. Worktrees created by coder therefore remain in
the cache volume and do not pollute the host checkout. No privileged mode or
Docker socket is used.

## Credentials and boundaries

Pass API keys at runtime, for example `-e OPENROUTER_API_KEY` or via an
uncommitted Compose environment file. `NINJA_CREDENTIAL_PASSWORD` is supported
for headless encrypted credentials. No credentials are copied into the image,
and `.env` files, caches, keys, and credential files are excluded from the
build context.

The image intentionally does not install host-authenticated `opencode`,
`claude`, or `aider` CLIs. One-shot agent `analyze` and `review` work with the
API-backed configuration. Coder execution that needs a local CLI requires a
deliberately extended image with that CLI installed, or an API-backed OpenCode
configuration. Never add an ad-hoc `curl | bash` installer.
