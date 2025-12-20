#!/usr/bin/env python3
"""
HTTP/SSE transport wrapper for ninja-cli-mcp daemon.

This allows a single daemon to serve multiple MCP clients over HTTP/SSE
instead of stdin/stdout.

Usage:
    python3 http_server.py --port 3000

Then configure Copilot with:
{
  "mcpServers": {
    "ninja-cli-mcp": {
      "type": "sse",
      "url": "http://localhost:3000/sse"
    }
  }
}
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import uvicorn
from sse_starlette import EventSourceResponse
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ninja_cli_mcp.tools import get_executor
from ninja_cli_mcp.models import QuickTaskRequest, SequentialPlanRequest, ParallelPlanRequest, RunTestsRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global executor instance
executor = None


async def handle_tool_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle MCP tool call."""
    global executor
    
    if executor is None:
        executor = get_executor()
    
    try:
        if tool_name == "ninja_quick_task":
            request = QuickTaskRequest(**arguments)
            result = await executor.execute_quick_task(request)
        elif tool_name == "execute_plan_sequential":
            request = SequentialPlanRequest(**arguments)
            result = await executor.execute_plan_sequential(request)
        elif tool_name == "execute_plan_parallel":
            request = ParallelPlanRequest(**arguments)
            result = await executor.execute_plan_parallel(request)
        elif tool_name == "run_tests":
            request = RunTestsRequest(**arguments)
            result = await executor.run_tests(request)
        else:
            return {"error": f"Unknown tool: {tool_name}"}
        
        return result.model_dump()
    
    except Exception as e:
        logger.error(f"Error executing {tool_name}: {e}")
        return {"error": str(e)}


async def sse_endpoint(request: Request):
    """SSE endpoint for MCP protocol."""
    async def event_generator():
        # Send initial connection message
        yield {
            "event": "message",
            "data": json.dumps({
                "jsonrpc": "2.0",
                "method": "server/initialized",
                "params": {"capabilities": {}}
            })
        }
        
        # Keep connection alive and handle messages
        # In a real implementation, this would properly handle MCP protocol
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("SSE connection closed")
    
    return EventSourceResponse(event_generator())


async def http_endpoint(request: Request):
    """HTTP endpoint for MCP tool calls."""
    body = await request.json()
    
    method = body.get("method")
    params = body.get("params", {})
    request_id = body.get("id")
    
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        result = await handle_tool_call(tool_name, arguments)
        
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        })
    
    elif method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {"name": "ninja_quick_task"},
                    {"name": "execute_plan_sequential"},
                    {"name": "execute_plan_parallel"},
                    {"name": "run_tests"},
                    {"name": "apply_patch"},
                ]
            }
        })
    
    return JSONResponse({"error": "Unknown method"}, status_code=400)


app = Starlette(
    routes=[
        Route("/sse", sse_endpoint),
        Route("/mcp", http_endpoint, methods=["POST"]),
    ]
)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    
    logger.info(f"Starting ninja-cli-mcp HTTP/SSE server on {args.host}:{args.port}")
    logger.info(f"SSE endpoint: http://{args.host}:{args.port}/sse")
    logger.info(f"HTTP endpoint: http://{args.host}:{args.port}/mcp")
    
    uvicorn.run(app, host=args.host, port=args.port)
