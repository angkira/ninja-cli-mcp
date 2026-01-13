"""MCP Server for Resources module."""

import json
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from ninja_resources.tools import ResourceToolExecutor
from ninja_resources.models import (
    ResourceCodebaseRequest,
    ResourceConfigRequest,
    ResourceDocsRequest,
)


# Initialize server
server = Server("ninja-resources")

# Initialize executor
_executor = ResourceToolExecutor()


# Define tools
TOOLS = [
    types.Tool(
        name="resource_codebase",
        description="Load your project's codebase as a queryable resource with file structure and function/class extraction",
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Path to project root",
                },
                "include_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File patterns to include (e.g., ['**/*.py', '**/*.js'])",
                },
                "exclude_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File patterns to exclude (default: common build/cache dirs)",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Maximum files to analyze (default: 1000)",
                },
                "summarize": {
                    "type": "boolean",
                    "description": "Generate file summaries (default: true)",
                },
            },
            "required": ["repo_root"],
        },
    ),
    types.Tool(
        name="resource_config",
        description="Load configuration files with automatic redaction of sensitive data",
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Path to project root",
                },
                "include": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Config files to load (e.g., ['.env.example', 'config.yaml'])",
                },
                "redact_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Patterns to redact (default: password, token, secret, api_key)",
                },
            },
            "required": ["repo_root", "include"],
        },
    ),
    types.Tool(
        name="resource_docs",
        description="Load documentation files as a queryable resource with section extraction",
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Path to project root",
                },
                "doc_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Markdown patterns to include (default: **/*.md)",
                },
                "include_structure": {
                    "type": "boolean",
                    "description": "Extract sections from markdown (default: true)",
                },
            },
            "required": ["repo_root"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return list of available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> Any:
    """Route tool calls to executor."""
    try:
        if name == "resource_codebase":
            request = ResourceCodebaseRequest(**arguments)
            result = await _executor.resource_codebase(request)
            return [types.TextContent(text=result.model_dump_json())]

        elif name == "resource_config":
            request = ResourceConfigRequest(**arguments)
            result = await _executor.resource_config(request)
            return [types.TextContent(text=result.model_dump_json())]

        elif name == "resource_docs":
            request = ResourceDocsRequest(**arguments)
            result = await _executor.resource_docs(request)
            return [types.TextContent(text=result.model_dump_json())]

        else:
            return [
                types.TextContent(
                    text=json.dumps({"error": f"Unknown tool: {name}"})
                )
            ]

    except Exception as e:
        return [types.TextContent(text=json.dumps({"error": str(e)}))]


async def main():
    """Run the MCP server."""
    # Server instructions
    server.instructions = """
Resources Module - Load project context as queryable resources.

## Available Tools

1. **resource_codebase** - Load your project's codebase
   - Analyzes project structure and files
   - Extracts functions and classes
   - Supports include/exclude patterns
   - Caches results for 1 hour

2. **resource_config** - Load configuration files
   - Loads environment and config files
   - Automatically redacts sensitive data (passwords, API keys, tokens)
   - All secrets replaced with ***REDACTED***

3. **resource_docs** - Load documentation
   - Extracts markdown files and sections
   - Builds documentation index
   - Supports nested documentation structures

## Usage Examples

1. Understand your project:
   resource_codebase({repo_root: "/path/to/project"})

2. Load config safely:
   resource_config({repo_root: "/path/to/project", include: [".env.example", "config.yaml"]})

3. Load documentation:
   resource_docs({repo_root: "/path/to/project"})

## Performance

- Small projects (<100 files): 100-200ms
- Medium projects (100-500 files): 300-500ms
- Large projects (500+ files): 500ms - 2s
- Results cached for 1 hour
"""

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.instructions)


def run() -> None:
    """Entry point for the ninja-resources MCP server."""
    import asyncio

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
