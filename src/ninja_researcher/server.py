"""
MCP stdio server for ninja-researcher module.

This module implements the Model Context Protocol (MCP) server that
exposes tools for web search and research tasks.

Usage:
    python -m ninja_researcher.server
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ninja_common.logging_utils import get_logger, setup_logging
from ninja_researcher.models import (
    DeepResearchRequest,
    FactCheckRequest,
    GenerateReportRequest,
    SummarizeSourcesRequest,
    WebSearchRequest,
)
from ninja_researcher.tools import get_executor

if TYPE_CHECKING:
    from collections.abc import Sequence


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions
TOOLS: list[Tool] = [
    Tool(
        name="researcher_deep_research",
        description=(
            "Perform comprehensive deep research on topics by decomposing them into "
            "sub-queries and using parallel search agents with Perplexity AI. Gathers multiple sources, "
            "identifies diverse perspectives, and builds detailed knowledge bases. "
            "\n\n"
            "Use when: researching complex topics, needing comprehensive coverage, "
            "gathering evidence from multiple angles, building knowledge bases, exploring "
            "trending topics, finding best practices, or when broad topic understanding is needed. "
            "\n\n"
            "Better than basic web search for: multi-faceted research, comparing alternatives, "
            "academic research, market analysis, technical deep-dives."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Research topic",
                },
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Specific queries (auto-generated if empty)",
                },
                "max_sources": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                    "description": "Maximum sources to gather",
                },
                "parallel_agents": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 4,
                    "description": "Number of parallel search agents",
                },
            },
            "required": ["topic"],
        },
    ),
    Tool(
        name="researcher_generate_report",
        description=(
            "Synthesize research sources into structured, comprehensive reports using parallel "
            "analysis agents. Analyzes multiple sources simultaneously, identifies key themes, "
            "and generates organized reports. "
            "\n\n"
            "Use when: creating research reports, summarizing findings, organizing information "
            "by topic, creating analysis documents, producing executive summaries, or synthesizing "
            "multiple sources into coherent narratives. "
            "\n\n"
            "⚠️ NOTE: This tool is under development."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Report topic",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Source documents to synthesize",
                },
                "report_type": {
                    "type": "string",
                    "enum": ["comprehensive", "summary", "technical", "executive"],
                    "default": "comprehensive",
                    "description": "Type of report to generate",
                },
                "parallel_agents": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 4,
                    "description": "Number of parallel synthesis agents",
                },
            },
            "required": ["topic", "sources"],
        },
    ),
    Tool(
        name="researcher_fact_check",
        description=(
            "Verify claims and statements against reliable web sources. Cross-references "
            "information, identifies supporting and contradicting evidence, and validates accuracy. "
            "\n\n"
            "Use when: validating statements, checking accuracy of claims, finding sources for "
            "assertions, identifying misinformation, verifying facts before publishing, or "
            "investigating controversial statements. "
            "\n\n"
            "⚠️ NOTE: This tool is under development."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "claim": {
                    "type": "string",
                    "description": "Claim to verify",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "URLs to check against (auto-search if empty)",
                },
            },
            "required": ["claim"],
        },
    ),
    Tool(
        name="researcher_summarize_sources",
        description=(
            "Extract key information and main points from multiple sources and create concise "
            "summaries. Condenses information while preserving essential insights and findings. "
            "\n\n"
            "Use when: condensing lengthy sources, extracting key insights, creating quick "
            "overviews, getting the gist of multiple articles, or preparing briefing materials. "
            "\n\n"
            "⚠️ NOTE: This tool is under development."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "URLs to summarize",
                },
                "max_length": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 5000,
                    "default": 500,
                    "description": "Maximum summary length in words",
                },
            },
            "required": ["urls"],
        },
    ),
]


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server(
        "ninja-researcher",
        version="0.2.0",
        instructions="""🔍 Ninja Researcher: Web Search & Report Generation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 WHAT RESEARCHER DOES:
   ✅ Search the web for information (DuckDuckGo, Serper/Google, Perplexity AI)
   ✅ Perform deep research with multiple queries
   ✅ Aggregate and deduplicate sources
   ✅ Generate comprehensive reports (coming soon)
   ✅ Fact-check claims (coming soon)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 AVAILABLE TOOLS:

• researcher_deep_research
  Multi-query research with parallel agents using Perplexity AI.
  Returns: Aggregated and deduplicated sources with AI-generated insights.

• researcher_generate_report (coming soon)
  Generate comprehensive reports from sources.

• researcher_fact_check (coming soon)
  Verify claims against web sources.

• researcher_summarize_sources (coming soon)
  Summarize multiple web sources.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 USAGE EXAMPLES:

1. Deep research:
   researcher_deep_research({
     "topic": "MCP protocol implementation",
     "max_sources": 20,
     "parallel_agents": 4
   })

3. Custom queries:
   researcher_deep_research({
     "topic": "AI code assistants",
     "queries": [
       "AI code assistants comparison",
       "Aider vs Cursor vs GitHub Copilot",
       "AI code assistant best practices"
     ],
     "max_sources": 30
   })

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ RATE LIMITS:
   • Web search: 30 calls/minute
   • Deep research: 10 calls/minute
   • Per-client tracking

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""",
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
        """Handle tool invocations."""
        client_id = "default"
        logger.info(f"[{client_id}] Tool called: {name}")

        executor = get_executor()

        try:
            if name == "researcher_deep_research":
                request = DeepResearchRequest(**arguments)
                result = await executor.deep_research(request, client_id=client_id)

            elif name == "researcher_generate_report":
                request = GenerateReportRequest(**arguments)
                result = await executor.generate_report(request, client_id=client_id)

            elif name == "researcher_fact_check":
                request = FactCheckRequest(**arguments)
                result = await executor.fact_check(request, client_id=client_id)

            elif name == "researcher_summarize_sources":
                request = SummarizeSourcesRequest(**arguments)
                result = await executor.summarize_sources(request, client_id=client_id)

            else:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": f"Unknown tool: {name}"}),
                    )
                ]

            # Serialize result to JSON
            result_json = result.model_dump()
            logger.info(
                f"[{client_id}] Tool {name} completed with status: {result_json.get('status', 'unknown')}"
            )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result_json, indent=2),
                )
            ]

        except Exception as e:
            logger.error(f"[{client_id}] Tool {name} failed: {e}", exc_info=True)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "error",
                            "error": str(e),
                            "error_type": type(e).__name__,
                        }
                    ),
                )
            ]

    return server


async def main_stdio() -> None:
    """Run the MCP server over stdio."""
    logger.info("Starting ninja-researcher server (stdio mode)")

    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        logger.info("Server ready, waiting for requests")
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def main_http(host: str, port: int) -> None:
    """Run the MCP server over HTTP with SSE."""
    from mcp.server.sse import SseServerTransport
    from starlette.requests import Request
    from starlette.responses import Response
    import uvicorn

    logger.info(f"Starting ninja-researcher server (HTTP/SSE mode) on {host}:{port}")

    server = create_server()
    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )
        return Response()

    async def handle_messages(scope, receive, send):
        await sse.handle_post_message(scope, receive, send)

    async def app(scope, receive, send):
        path = scope.get("path", "")
        if path == "/sse":
            request = Request(scope, receive, send)
            await handle_sse(request)
        elif path == "/messages" and scope.get("method") == "POST":
            await handle_messages(scope, receive, send)
        else:
            await Response("Not Found", status_code=404)(scope, receive, send)

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


def run() -> None:
    """Entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="Ninja Researcher MCP Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run server in HTTP/SSE mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8101,
        help="Port for HTTP server (default: 8101)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    args = parser.parse_args()

    try:
        if args.http:
            asyncio.run(main_http(args.host, args.port))
        else:
            asyncio.run(main_stdio())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
