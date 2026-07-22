"""Point d'entrée HTTP — BOSSCORE MCP PACK.
Streamable HTTP (MCP 2025-03-26+) pour chatgpt.com et clients distants.
Un seul endpoint /sse/ — POST (Streamable HTTP) + GET (fallback SSE legacy)."""
import sys, argparse

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))

from mcp.server import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport
from starlette.applications import Starlette
from starlette.routing import Route

from tools.schemas import tool_list
from tools.handlers import dispatch

server = Server("bosscore")


@server.list_tools()
async def handle_list_tools():
    return tool_list()


@server.call_tool()
async def handle_call_tool(name, arguments):
    return await dispatch(name, arguments)


async def handle_mcp(scope, receive, send):
    """ASGI raw handler — Streamable HTTP (POST) + fallback SSE legacy (GET).
    handle_request() gère les deux protocoles : si le POST InitializeRequest
    arrive, Streamable HTTP ; si GET, fallback SSE avec endpoint event.
    mcp_session_id=None = mode stateless (MCP 2026-07-28)."""
    transport = StreamableHTTPServerTransport(mcp_session_id=None)
    await transport.handle_request(scope, receive, send)


def main():
    parser = argparse.ArgumentParser(description="BOSSCORE MCP Pack — Streamable HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    app = Starlette(routes=[
        Route("/sse/", endpoint=handle_mcp),
    ])

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
