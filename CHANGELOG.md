# Changelog

## 1.0.1 - 2026-09-08

- Fixed the GitHub release workflow to publish to PyPI with the configured API
  token secret.
- Updated Docker image defaults and package metadata for the 1.0.1 release.

## 1.0.0 - 2026-09-08

- Added a non-root Python 3.12 container image with local package installation.
- Added Compose profiles for coder, researcher, secretary, and agent services.
- Added local-only port bindings, read-only mounts where safe, named config and
  cache volumes, and HTTP/SSE healthchecks.
- Documented runtime-only credentials and the limitation that host-authenticated
  coding CLIs are not included in the image.

### Security and migration notes

- Do not put API keys in the Dockerfile, Compose file, image, or build context.
- Existing host configuration is not automatically mounted; use the named
  volumes or pass `NINJA_CREDENTIAL_PASSWORD` at runtime.
- Coder worktrees are stored under the Ninja cache volume and must be merged or
  pruned deliberately.
