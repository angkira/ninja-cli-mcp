#!/usr/bin/env python3
"""
stdio-to-HTTP proxy for ninja-cli-mcp.

This proxy allows Copilot CLI (which uses stdio) to communicate with
the HTTP/SSE daemon. It reads JSON-RPC from stdin, forwards to HTTP,
and writes responses to stdout.

Architecture:
  Copilot CLI → stdio → this proxy → HTTP → daemon → aider
"""

import asyncio
import json
import sys
from typing import Any
from pathlib import Path
import os

import httpx

# Configuration
DAEMON_URL = os.environ.get("NINJA_HTTP_URL", "http://127.0.0.1:8947/mcp")
TIMEOUT = 600  # 10 minutes for long-running tasks


async def forward_request(request: dict[str, Any]) -> dict[str, Any]:
    """Forward JSON-RPC request to HTTP daemon."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.post(DAEMON_URL, json=request)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"Proxy error: {str(e)}"
                }
            }


async def stdio_loop():
    """Main loop: read from stdin, forward to HTTP, write to stdout."""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        try:
            # Read line from stdin
            line = await reader.readline()
            if not line:
                break

            line = line.decode('utf-8').strip()
            if not line:
                continue

            # Parse JSON-RPC request
            request = json.loads(line)
            
            # Forward to daemon
            response = await forward_request(request)
            
            # Write response to stdout
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {str(e)}"
                }
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()
        except Exception as e:
            # Log to stderr (won't interfere with JSON-RPC on stdout)
            sys.stderr.write(f"Proxy error: {e}\n")
            sys.stderr.flush()


def main():
    """Entry point."""
    # Ensure daemon is running
    daemon_pid_file = Path.home() / ".cache/ninja-cli-mcp/daemon.pid"
    if not daemon_pid_file.exists():
        sys.stderr.write("Warning: Daemon PID file not found. Is daemon running?\n")
        sys.stderr.write("Start daemon: systemctl --user start ninja-cli-mcp\n")
        sys.stderr.flush()
    
    # Run stdio loop
    try:
        asyncio.run(stdio_loop())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
