#!/usr/bin/env bash
# Post-install hook - automatically restart MCP servers after update

set -euo pipefail

echo "🔄 Post-install: Restarting MCP servers with new code..."

# Kill old servers
pkill -f "ninja_coder.server" 2>/dev/null || true
pkill -f "ninja_researcher.server" 2>/dev/null || true
pkill -f "ninja_secretary.server" 2>/dev/null || true
pkill -f "ninja_prompts.server" 2>/dev/null || true
pkill -f "ninja_resources.server" 2>/dev/null || true

sleep 2

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Start servers with new code
echo "Starting ninja-coder..."
nohup uv run python -m ninja_coder.server --http --port 8100 > /tmp/ninja-coder.log 2>&1 &

echo "Starting ninja-researcher..."
nohup uv run python -m ninja_researcher.server --http --port 8101 > /tmp/ninja-researcher.log 2>&1 &

echo "Starting ninja-secretary..."
nohup uv run python -m ninja_secretary.server --http --port 8102 > /tmp/ninja-secretary.log 2>&1 &

echo "Starting ninja-prompts..."
nohup uv run python -m ninja_prompts.server --http --port 8107 > /tmp/ninja-prompts.log 2>&1 &

sleep 3

# Verify servers are running
if ps aux | grep "ninja.*server" | grep -v grep | grep -q ".venv"; then
    echo "✅ All servers restarted successfully with new code"
    ps aux | grep "ninja.*server" | grep -v grep | grep ".venv" | awk '{print "  →", $2, $11, $13}'
else
    echo "❌ Warning: Servers may not be running correctly"
fi
