#!/bin/bash
# Quick proxy connection test

set -e

echo "Testing proxy connection to coder daemon..."

# Create a test JSON-RPC message
TEST_MSG='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"1.0.0","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'

# Run proxy in background and send test message
(
  echo "$TEST_MSG"
  sleep 1
) | uv --directory /Users/iuriimedvedev/Project/ninja-coder/ninja-cli-mcp run ninja-daemon connect coder &

PROXY_PID=$!

# Wait briefly
sleep 2

# Kill the proxy process
kill $PROXY_PID 2>/dev/null || true

echo "Proxy test completed"
