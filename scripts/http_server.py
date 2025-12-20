#!/usr/bin/env python3
"""
HTTP/SSE transport wrapper for ninja-cli-mcp daemon implementing proper MCP protocol.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ninja_cli_mcp.tools import get_executor, get_tool_definitions
from ninja_cli_mcp.models import (
    QuickTaskRequest,
    SequentialPlanRequest,
    ParallelPlanRequest,
    RunTestsRequest,
)

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
            result = await executor.quick_task(request)
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

        return {"content": [{"type": "text", "text": json.dumps(result.model_dump(), indent=2)}]}

    except Exception as e:
        logger.error(f"Error executing {tool_name}: {e}", exc_info=True)
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}


async def mcp_endpoint(request: Request):
    """Unified MCP endpoint handling all JSON-RPC methods."""
    body = await request.json()

    method = body.get("method")
    params = body.get("params", {})
    request_id = body.get("id")

    logger.info(f"MCP request: method={method}, id={request_id}")

    # Handle initialize
    if method == "initialize":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "ninja-cli-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            }
        )

    # Handle tools/list
    elif method == "tools/list":
        tools = get_tool_definitions()
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}})

    # Handle tools/call
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        result = await handle_tool_call(tool_name, arguments)

        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})

    else:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            },
            status_code=400,
        )


app = Starlette(
    routes=[
        Route("/sse", mcp_endpoint, methods=["GET", "POST"]),
        Route("/mcp", mcp_endpoint, methods=["POST"]),
    ]
)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    logger.info(f"Starting ninja-cli-mcp HTTP/SSE server on {args.host}:{args.port}")
    logger.info(f"MCP endpoints: http://{args.host}:{args.port}/sse and /mcp")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
