# Running daemons under systemd --user

The module servers (coder 8100, researcher 8101, secretary 8102, agent 8103)
should run as supervised user services, not from an interactive terminal.
A daemon started from a shell dies with that shell/session and may prompt for
the secret-store password on a TTY; under systemd it is restarted
automatically (`Restart=always`) and unlocks the store without a prompt.

Never start the daemons from an interactive terminal on a machine that uses
this setup; use `systemctl --user` instead.

## Files

| Repo file | Install location |
|---|---|
| `scripts/systemd/ninja-mcp@.service` | `~/.config/systemd/user/ninja-mcp@.service` |
| `scripts/ninja-mcp-serve` | `~/.local/bin/ninja-mcp-serve` |

The template unit (`%i` = module name) runs `%h/.local/bin/ninja-mcp-serve %i`
with `Restart=always`. The launcher sources `~/.ninja-mcp.env` (shell syntax,
so `export X=...` lines work, which systemd's `EnvironmentFile=` cannot parse),
extends `PATH` with the usual user CLI directories, and `exec`s the module
HTTP server so systemd supervises the real process. Set `NINJA_MCP_PYTHON` to
use a Python other than the `uv tool` install
(`$HOME/.local/share/uv/tools/ninja-mcp/bin/python3`).

Secrets are read from the encrypted store (`~/.ninja/credentials.db`) and are
never kept in `~/.ninja-mcp.env`. A passwordless store opens without a
password; a password-protected store needs a systemd credential or
`NINJA_STORE_PASSWORD_FILE` (see `docs/SECRETS.md`).

## Install

```bash
install -Dm 0755 scripts/ninja-mcp-serve ~/.local/bin/ninja-mcp-serve
install -Dm 0644 scripts/systemd/ninja-mcp@.service ~/.config/systemd/user/ninja-mcp@.service
systemctl --user daemon-reload
systemctl --user enable --now ninja-mcp@coder ninja-mcp@researcher ninja-mcp@secretary ninja-mcp@agent
loginctl enable-linger "$USER"   # keep running after logout
```

Check: `systemctl --user status 'ninja-mcp@*'` and
`journalctl --user -u ninja-mcp@researcher -f`.

This template supersedes the older oneshot `scripts/ninja-cli-mcp.service`
(installed by `scripts/install_service.sh`); do not run both for the same
ports.
