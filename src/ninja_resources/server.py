import argparse
import asyncio
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    EmbeddedResource,
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
    TextResourceContents,
)


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_server() -> Server:
    """Create and configure the MCP server with all tools registered."""
    server = Server("ninja-resources")

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        return [
            Prompt(
                name="resource_template",
                description="Template for creating new resources",
                arguments=[
                    PromptArgument(
                        name="resource_type",
                        description="Type of resource to create",
                        required=True,
                    )
                ],
            )
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        if name == "resource_template":
            resource_type = arguments.get("resource_type", "default") if arguments else "default"
            return GetPromptResult(
                description=f"Template for {resource_type} resource",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text", text=f"Create a {resource_type} resource template"
                        ),
                    )
                ],
            )
        raise ValueError(f"Unknown prompt: {name}")

    @server.list_resources()
    async def list_resources() -> list[EmbeddedResource]:
        return [
            EmbeddedResource(
                uri="ninja://templates/python",
                name="Python Template",
                description="Template for Python files",
                mimeType="text/x-python",
            ),
            EmbeddedResource(
                uri="ninja://templates/javascript",
                name="JavaScript Template",
                description="Template for JavaScript files",
                mimeType="application/javascript",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> TextResourceContents:
        if uri == "ninja://templates/python":
            content = '''#!/usr/bin/env python3
"""
Python template file
"""

def main():
    print("Hello from Python template!")

if __name__ == "__main__":
    main()
'''
        elif uri == "ninja://templates/javascript":
            content = """#!/usr/bin/env node
/**
 * JavaScript template file
 */

function main() {
    console.log("Hello from JavaScript template!");
}

if (require.main === module) {
    main();
}
"""
        else:
            raise ValueError(f"Unknown resource: {uri}")

        return TextResourceContents(uri=uri, text=content)

    return server


async def main_stdio():
    """Run the server over stdio - original main function."""
    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def main_http(host: str, port: int) -> None:
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.requests import Request
    from starlette.responses import Response

    server = create_server()  # Create fresh server instance
    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        try:
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await server.run(streams[0], streams[1], server.create_initialization_options())
        except Exception as e:
            # Handle any errors in SSE connection gracefully
            logger.error(f"Error in SSE handler: {e}", exc_info=True)
        return Response()

    async def handle_messages(scope, receive, send):
        try:
            await sse.handle_post_message(scope, receive, send)
        except Exception as e:
            # Handle closed connections and other errors gracefully
            logger.error(f"Error handling SSE message: {e}")
            try:
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [[b"content-type", b"application/json"]],
                })
                import json
                await send({
                    "type": "http.response.body",
                    "body": json.dumps({"error": str(e)}).encode(),
                })
            except Exception:
                # Connection already closed, ignore
                pass

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


def run():
    """Entry point for the server."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="Run in HTTP mode")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")

    args = parser.parse_args()

    try:
        if args.http:
            asyncio.run(main_http(args.host, args.port))
        else:
            asyncio.run(main_stdio())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
