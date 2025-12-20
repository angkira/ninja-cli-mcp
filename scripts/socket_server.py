#!/usr/bin/env python3
"""
Socket-based MCP server that allows multiple clients to connect to a single daemon.

Architecture:
- Daemon runs this script, listens on Unix socket
- Each client connects via socket
- Server spawns a new handler for each client connection
- All clients share the same ninja-cli-mcp tools instance

Usage:
    python3 socket_server.py --socket /tmp/ninja-cli-mcp.sock
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ninja_cli_mcp.server import app, logger as server_logger

SOCKET_PATH = "/tmp/ninja-cli-mcp.sock"

logger = logging.getLogger(__name__)


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle a single client connection."""
    addr = writer.get_extra_info('peername')
    logger.info(f"Client connected: {addr}")
    
    try:
        while True:
            # Read JSON-RPC message
            line = await reader.readline()
            if not line:
                break
                
            try:
                message = json.loads(line.decode())
                logger.debug(f"Received from {addr}: {message.get('method', 'unknown')}")
                
                # Forward to MCP server (this is a simplified version)
                # In reality, we'd need to properly handle the MCP protocol
                # For now, just echo back
                response = {"jsonrpc": "2.0", "id": message.get("id"), "result": {"status": "ok"}}
                writer.write(json.dumps(response).encode() + b'\n')
                await writer.drain()
                
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from {addr}: {e}")
                break
                
    except Exception as e:
        logger.error(f"Error handling client {addr}: {e}")
    finally:
        logger.info(f"Client disconnected: {addr}")
        writer.close()
        await writer.wait_closed()


async def main():
    """Start the socket server."""
    # Remove old socket if exists
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
    
    server = await asyncio.start_unix_server(handle_client, path=SOCKET_PATH)
    
    # Make socket accessible
    os.chmod(SOCKET_PATH, 0o666)
    
    logger.info(f"ninja-cli-mcp daemon listening on {SOCKET_PATH}")
    
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
