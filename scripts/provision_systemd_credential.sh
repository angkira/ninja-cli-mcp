#!/usr/bin/env bash
#
# provision_systemd_credential.sh - Supply the encrypted-store password to the
# ninja-cli-mcp user service via a systemd credential (no env, no plaintext).
#
# Creates an encrypted credential with `systemd-creds` and a systemd drop-in
# that loads it. The daemon reads it from $CREDENTIALS_DIRECTORY at startup
# (see ninja_config.secrets_store._read_systemd_credential). The password is
# then never present in the unit file, environment, or on disk in plaintext.
#
# Usage: ./scripts/provision_systemd_credential.sh
# Remove: delete ~/.config/systemd/user/ninja-cli-mcp.service.d/credential.conf
#         and ~/.config/ninja-mcp/store-password.cred, then daemon-reload.

set -euo pipefail

UNIT="ninja-cli-mcp.service"
CRED_ID="ninja-store-password"
DROPIN_DIR="$HOME/.config/systemd/user/${UNIT}.d"
CRED_DIR="$HOME/.config/ninja-mcp"
CRED_FILE="$CRED_DIR/store-password.cred"

if ! command -v systemd-creds >/dev/null 2>&1; then
    echo "systemd-creds not found (systemd not installed?)." >&2
    exit 1
fi

mkdir -p "$DROPIN_DIR" "$CRED_DIR"

read -rsp "Encrypted store password: " PASSWORD
echo
if [ -z "$PASSWORD" ]; then
    echo "Empty password — aborting." >&2
    exit 1
fi

# Encrypt the password for THIS user's service (systemd credential, not plaintext).
printf '%s' "$PASSWORD" | systemd-creds --user encrypt --name="$CRED_ID" - "$CRED_FILE"
unset PASSWORD

cat > "$DROPIN_DIR/credential.conf" <<EOF
[Service]
LoadCredentialEncrypted=${CRED_ID}:${CRED_FILE}
EOF

systemctl --user daemon-reload
echo "Provisioned ${CRED_FILE} and ${DROPIN_DIR}/credential.conf"
echo "Apply with: systemctl --user restart ${UNIT}"
