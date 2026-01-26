#!/usr/bin/env bash
#
# Clean ninja-mcp env overrides from Claude Code config
#
# All configuration should be centralized in ~/.ninja-mcp.env
# This script removes env from ninja-* servers in ~/.claude.json
#

set -euo pipefail

CLAUDE_CONFIG="$HOME/.claude.json"

if [[ ! -f "$CLAUDE_CONFIG" ]]; then
    echo "✗ Claude config not found at $CLAUDE_CONFIG"
    exit 1
fi

echo "Cleaning ninja-mcp env overrides from Claude Code config..."
echo ""

python3 << 'EOF'
import json
import sys
from pathlib import Path

claude_config = Path.home() / ".claude.json"

try:
    with open(claude_config) as f:
        config = json.load(f)

    if "mcpServers" not in config:
        print("✗ No mcpServers found in config")
        sys.exit(1)

    # Remove env from all ninja servers
    cleaned = []
    for server in ["ninja-coder", "ninja-researcher", "ninja-secretary", "ninja-resources", "ninja-prompts"]:
        if server in config["mcpServers"]:
            if "env" in config["mcpServers"][server]:
                del config["mcpServers"][server]["env"]
                cleaned.append(server)
                print(f"✓ Cleaned {server}")
            else:
                print(f"  {server} (already clean)")

    if cleaned:
        with open(claude_config, "w") as f:
            json.dump(config, f, indent=2)
        print(f"\n✓ Cleaned {len(cleaned)} server(s)")
        print(f"\nAll ninja servers now read from ~/.ninja-mcp.env")
        print("Restart Claude Code to apply changes")
    else:
        print("\n✓ Config already clean - no changes needed")

except Exception as e:
    print(f"✗ Error: {e}", file=sys.stderr)
    sys.exit(1)
EOF
