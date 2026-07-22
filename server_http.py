"""Point d'entrée HTTP/SSE — BOSSCORE MCP PACK pour chatgpt.com et clients distants."""
import os, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import Response

from tools.schemas import tool_list
from tools.handlers import dispatch

server = Server("bosscore")
sse = SseServerTransport("/messages/")


@server.list_tools()
async def handle_list_tools():
    return tool_list()

@server.call_tool()
async def handle_call_tool(name, arguments):
    return await dispatch(name, arguments)


async def handle_sse(request: Request) -> Response:
    """SSE endpoint — Route, pas Mount (évite contamination root_path)."""
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
    return Response()  # requis par Starlette Route


def main():
    parser = argparse.ArgumentParser(description="BOSSCORE MCP Pack — HTTP/SSE")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    app = Starlette(routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ])

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
