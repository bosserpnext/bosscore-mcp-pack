"""Point d'entrée du BOSSCORE MCP PACK — WordPress, fichiers, déploiement cPanel.

Lancé par opencode :
    python.exe C:\\Users\\Takoudjou\\.config\\opencode\\bosscore-mcp-pack\\server.py
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server

from tools.schemas import tool_list
from tools.handlers import dispatch

server = Server("bosscore")


@server.list_tools()
async def handle_list_tools():
    return tool_list()


@server.call_tool()
async def handle_call_tool(name, arguments):
    return await dispatch(name, arguments)


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
