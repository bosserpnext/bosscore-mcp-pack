"""HTTP entry point for the bosscore-mcp-http console script.
Packaged version — delegates to the unified app.py runtime.
"""
import os
import sys


def cli():
    """Launch Streamable HTTP server with auth middleware.

    Usage: bosscore-mcp-http [--host 127.0.0.1] [--port 8765] [--profile full]
    """
    # Ensure the package root is importable
    from .app import build_server
    from .core.auth import AuthMiddleware
    from .core.logging import setup_logging
    from .settings import Settings

    import argparse

    parser = argparse.ArgumentParser(description="BOSSCORE MCP Pack — Streamable HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--profile", default=os.getenv("BOSSCORE_MCP_PROFILE", "full"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    os.environ["BOSSCORE_MCP_PROFILE"] = args.profile
    setup_logging(args.log_level)

    settings = Settings.from_env()
    server = build_server(settings)

    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    session_manager = StreamableHTTPSessionManager(app=server, stateless=True)

    from starlette.applications import Starlette
    from starlette.routing import Mount

    class MCPEndpoint:
        def __init__(self, sm):
            self._sm = sm

        async def __call__(self, scope, receive, send):
            await self._sm.handle_request(scope, receive, send)

    app = Starlette(
        routes=[Mount("/sse/", app=MCPEndpoint(session_manager))],
        lifespan=lambda app: session_manager.run(),
    )
    app.add_middleware(AuthMiddleware)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())
