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

if TYPE_CHECKING:
    from collections.abc import Sequence


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions
TOOLS: list[Tool] = [
    Tool(
        name="researcher_web_search",
        description=(
            "Search the web for information using various search providers. "
            "Returns a list of relevant search results with titles, URLs, and snippets."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                    "description": "Maximum number of results to return",
                },
                "search_provider": {
                    "type": "string",
                    "enum": ["tavily", "duckduckgo", "serper", "brave"],
                    "default": "tavily",
                    "description": "Search provider to use",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="researcher_deep_research",
        description=(
            "Perform deep research on a topic using multiple queries and parallel agents. "
            "Automatically decomposes the topic into sub-queries and gathers comprehensive sources."
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
                },
                "parallel_agents": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 4,
                },
            },
            "required": ["topic"],
        },
    ),
    Tool(
        name="researcher_generate_report",
        description=(
            "Generate a comprehensive report from research sources using parallel sub-agents. "
            "Each agent analyzes a subset of sources, then results are synthesized."
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
                },
                "parallel_agents": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 4,
                },
            },
            "required": ["topic", "sources"],
        },
    ),
]


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server(
        "ninja-researcher",
        version="0.2.0",
        instructions="""🔍 Ninja Researcher: Web Search & Report Generation

This module provides tools for web search and research tasks.

Available tools:
• researcher_web_search - Search the web for information
• researcher_deep_research - Multi-query research with synthesis
• researcher_generate_report - Generate reports from sources

⚠️ NOTE: This module is under development. Full functionality coming soon.""",
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
        """Handle tool invocations."""
        logger.info(f"Tool called: {name}")

        # Placeholder implementation
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "status": "error",
                        "error": "Researcher module is under development",
                        "message": "This tool is not yet implemented. Coming soon!",
                    }
                ),
            )
        ]

    return server


async def main() -> None:
    """Run the MCP server."""
    logger.info("Starting ninja-researcher server")

    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        logger.info("Server ready, waiting for requests")
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run() -> None:
    """Entry point for running the server."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
