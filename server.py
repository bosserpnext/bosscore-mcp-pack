"""Point d'entrée stdio — BOSSCORE MCP PACK.
Délègue toute la logique au runtime unifié src/bosscore_mcp/app.py.
"""
import asyncio
from mcp.server.stdio import stdio_server


async def main():
    from bosscore_mcp.app import build_server
    from bosscore_mcp.settings import Settings

    settings = Settings.from_env()
    server = build_server(settings)

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
