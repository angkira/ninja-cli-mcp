#!/usr/bin/env bash
#
# install_service.sh - Install & enable the ninja-cli-mcp systemd user service.
#
# Installs a PATH-aware daemon launcher to ~/.local/bin and the unit to
# ~/.config/systemd/user, then enables it to start on login/boot. Enabling
# linger is attempted so the daemons also survive logout.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_NAME="ninja-cli-mcp.service"
UNIT_DIR="$HOME/.config/systemd/user"

if ! command -v systemctl >/dev/null 2>&1 || ! systemctl --version >/dev/null 2>&1; then
    echo "systemd not available — cannot install the user service." >&2
    exit 1
fi

mkdir -p "$UNIT_DIR" "$HOME/.local/bin"
install -m 0755 "$SCRIPT_DIR/run_daemons.sh" "$HOME/.local/bin/ninja-mcp-daemons"
install -m 0644 "$SCRIPT_DIR/ninja-cli-mcp.service" "$UNIT_DIR/$UNIT_NAME"

systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"

# Linger lets user services run without an active login session.
loginctl enable-linger "$USER" 2>/dev/null || true

echo "Installed: $UNIT_DIR/$UNIT_NAME (enabled, started)"
systemctl --user --no-pager status "$UNIT_NAME" || true
