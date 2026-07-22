"""Point d'entrée HTTP Streamable — BOSSCORE MCP PACK.
Utilise le runtime unifié src/bosscore_mcp/app.py.
Protection : Origin validation + Bearer token + scopes via AuthMiddleware.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

from src.bosscore_mcp.app import build_server
from src.bosscore_mcp.core.auth import AuthMiddleware
from src.bosscore_mcp.core.logging import setup_logging
from src.bosscore_mcp.settings import Settings


class MCPEndpoint:
    """Raw ASGI endpoint — Streamable HTTP. Délègue au session manager."""

    def __init__(self, session_manager: StreamableHTTPSessionManager):
        self._sm = session_manager

    async def __call__(self, scope, receive, send):
        await self._sm.handle_request(scope, receive, send)


def main():
    parser = argparse.ArgumentParser(description="BOSSCORE MCP Pack — Streamable HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--profile", default=os.getenv("BOSSCORE_MCP_PROFILE", "full"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    # Force profile from CLI or env
    os.environ["BOSSCORE_MCP_PROFILE"] = args.profile

    setup_logging(args.log_level)

    settings = Settings.from_env()
    server = build_server(settings)
    session_manager = StreamableHTTPSessionManager(app=server, stateless=True)

    app = Starlette(
        routes=[
            Mount("/sse/", app=MCPEndpoint(session_manager)),
        ],
        lifespan=lambda app: session_manager.run(),
    )

    # Wrap with auth middleware (Origin + Bearer + Scopes)
    app.add_middleware(AuthMiddleware)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())


if __name__ == "__main__":
    main()
