"""Point d'entrée HTTP/SSE — BOSSCORE MCP PACK pour chatgpt.com et clients distants.

Usage sur le VPS :
    source ~/repos/companies/.env
    python3 server_http.py --host 127.0.0.1 --port 8765
    # Puis proxy NGINX vers ce port, ou tunnel SSH pour test local
"""
import os
import sys
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response
from starlette.requests import Request

from tools.schemas import tool_list
from tools.handlers import dispatch

server = Server("bosscore")
sse = SseServerTransport("/messages")


@server.list_tools()
async def handle_list_tools():
    return tool_list()


@server.call_tool()
async def handle_call_tool(name, arguments):
    return await dispatch(name, arguments)


async def handle_sse(request: Request):
    """Endpoint SSE — connexion entrante depuis chatgpt.com."""
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as (read, write):
        await server.run(read, write, server.create_initialization_options())


async def health(request: Request):
    """Health check."""
    return Response("OK", media_type="text/plain")


def main():
    parser = argparse.ArgumentParser(description="BOSSCORE MCP Pack — HTTP/SSE Server")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute")
    parser.add_argument("--port", type=int, default=8765, help="Port d'écoute")
    args = parser.parse_args()

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/health", endpoint=health),
            Mount("/messages", app=sse.handle_post_message),
        ]
    )

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
