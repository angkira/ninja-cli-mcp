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
        name="researcher_web_search",
        description=(
            "Search the web for information using DuckDuckGo or Serper.dev (Google Search). "
            "Returns a list of relevant search results with titles, URLs, and snippets. "
            "\n\n"
            "Use this for: Finding information, gathering sources, researching topics. "
            "\n\n"
            "Providers: "
            "- duckduckgo (free, no API key) "
            "- serper (Google Search, requires SERPER_API_KEY)"
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
                    "enum": ["duckduckgo", "serper"],
                    "default": "duckduckgo",
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
            "Automatically decomposes the topic into sub-queries and gathers comprehensive sources. "
            "\n\n"
            "Use this for: Comprehensive research, gathering multiple perspectives, "
            "building knowledge base on a topic."
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
            "Generate a comprehensive report from research sources using parallel sub-agents. "
            "Each agent analyzes a subset of sources, then results are synthesized. "
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
            "Verify a claim against web sources. "
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
            "Summarize multiple web sources into a cohesive summary. "
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
   ✅ Search the web for information (DuckDuckGo, Serper/Google)
   ✅ Perform deep research with multiple queries
   ✅ Aggregate and deduplicate sources
   ✅ Generate comprehensive reports (coming soon)
   ✅ Fact-check claims (coming soon)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 AVAILABLE TOOLS:

• researcher_web_search
  Search the web using DuckDuckGo (free) or Serper.dev (Google Search).
  Returns: List of search results with titles, URLs, snippets.

• researcher_deep_research
  Multi-query research with parallel agents.
  Returns: Aggregated and deduplicated sources.

• researcher_generate_report (coming soon)
  Generate comprehensive reports from sources.

• researcher_fact_check (coming soon)
  Verify claims against web sources.

• researcher_summarize_sources (coming soon)
  Summarize multiple web sources.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔑 SEARCH PROVIDERS:

• DuckDuckGo (default)
  - Free, no API key required
  - Good for general searches
  - Rate limited by DuckDuckGo

• Serper.dev (Google Search)
  - Requires SERPER_API_KEY environment variable
  - Higher quality results (Google Search)
  - Free tier: 2,500 searches/month
  - Get key from: https://serper.dev

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 USAGE EXAMPLES:

1. Simple web search:
   researcher_web_search({
     "query": "Python async best practices",
     "max_results": 10,
     "search_provider": "duckduckgo"
   })

2. Deep research:
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
            if name == "researcher_web_search":
                request = WebSearchRequest(**arguments)
                result = await executor.web_search(request, client_id=client_id)

            elif name == "researcher_deep_research":
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
