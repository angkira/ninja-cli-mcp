"""MCP Server for Prompts module."""

import json
import sys
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from ninja_prompts.tools import PromptToolExecutor
from ninja_prompts.models import (
    PromptRegistryRequest,
    PromptSuggestRequest,
    PromptChainRequest,
)


# Initialize server
server = Server("ninja-prompts")

# Initialize executor
_executor = PromptToolExecutor()


# Define tools
TOOLS = [
    types.Tool(
        name="prompt_registry",
        description="Manage prompt templates: list, get, create, update, delete",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "get", "create", "update", "delete"],
                    "description": "Action to perform",
                },
                "prompt_id": {
                    "type": "string",
                    "description": "Prompt identifier (required for get/update/delete)",
                },
                "name": {
                    "type": "string",
                    "description": "Prompt name (required for create)",
                },
                "description": {
                    "type": "string",
                    "description": "Prompt description",
                },
                "template": {
                    "type": "string",
                    "description": "Prompt template with {{variable}} placeholders",
                },
                "variables": {
                    "type": "array",
                    "description": "List of template variables",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization",
                },
            },
            "required": ["action"],
        },
    ),
    types.Tool(
        name="prompt_suggest",
        description="Get AI-powered suggestions for relevant prompts based on context",
        inputSchema={
            "type": "object",
            "properties": {
                "context": {
                    "type": "object",
                    "description": "Context for suggestions (task, language, file_type, etc.)",
                },
                "max_suggestions": {
                    "type": "integer",
                    "description": "Maximum number of suggestions to return",
                },
            },
        },
    ),
    types.Tool(
        name="prompt_chain",
        description="Compose and execute multi-step prompt workflows",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "execute"],
                    "description": "Action to perform",
                },
                "chain_id": {
                    "type": "string",
                    "description": "Unique chain identifier",
                },
                "steps": {
                    "type": "array",
                    "description": "List of workflow steps",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Step name",
                            },
                            "prompt_id": {
                                "type": "string",
                                "description": "Prompt to execute",
                            },
                            "variables": {
                                "type": "object",
                                "description": "Variables for this step",
                            },
                        },
                    },
                },
            },
            "required": ["action"],
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
        if name == "prompt_registry":
            request = PromptRegistryRequest(**arguments)
            result = await _executor.prompt_registry(request)
            return [types.TextContent(text=result.model_dump_json())]

        elif name == "prompt_suggest":
            request = PromptSuggestRequest(**arguments)
            result = await _executor.prompt_suggest(request)
            return [types.TextContent(text=result.model_dump_json())]

        elif name == "prompt_chain":
            request = PromptChainRequest(**arguments)
            result = await _executor.prompt_chain(request)
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
Prompts Module - Manage reusable prompt templates and multi-step workflows.

## Available Tools

1. **prompt_registry** - Manage prompt templates
   - list: List all available prompts
   - get: Retrieve a specific prompt
   - create: Create a new prompt
   - delete: Delete a prompt

2. **prompt_suggest** - Get relevant prompt suggestions
   - Analyze context and suggest matching prompts
   - Based on task, language, file_type, etc.

3. **prompt_chain** - Execute multi-step workflows
   - Compose prompts in sequence
   - Pass outputs from one step to the next
   - Use {{prev.step_name}} syntax for output references

## Built-in Prompts

- code-review-v1: Professional code review
- bug-debugging-v1: Systematic bug investigation
- feature-implementation-v1: Complete feature workflow
- architecture-design-v1: System architecture design

## Example Usage

1. Suggest prompts: prompt_suggest({context: {task: "code-review", language: "python"}})
2. Get a prompt: prompt_registry({action: "get", prompt_id: "code-review-v1"})
3. Execute chain: prompt_chain({action: "execute", steps: [...]})
"""

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.instructions)


def run() -> None:
    """Entry point for the ninja-prompts MCP server."""
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
