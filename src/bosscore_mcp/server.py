"""MCP composition root and profile selection."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from mcp.server import Server
from mcp.server.stdio import stdio_server

from .core.registry import ToolRegistry
from .core.results import failure, success
from .documents.policy import PathPolicy
from .documents.provider import DocumentProvider
from .documents.service import DocumentService
from .settings import Settings
from .wordpress.client import WordPressClient
from .wordpress.provider import WordPressProvider


@dataclass(slots=True)
class Runtime:
    registry: ToolRegistry
    clients: list[WordPressClient] = field(default_factory=list)

    async def close(self) -> None:
        for client in self.clients:
            await client.close()


def build_runtime(settings: Settings) -> Runtime:
    registry = ToolRegistry()
    clients: list[WordPressClient] = []

    if settings.profile in {"wordpress", "full"}:
        settings.require_wordpress()
        client = WordPressClient(
            settings.wordpress_url,
            settings.wordpress_username,
            settings.wordpress_password,
        )
        clients.append(client)
        registry.extend(WordPressProvider(client).specs())

    if settings.profile in {"files", "full"}:
        settings.require_file_roots()
        policy = PathPolicy(settings.file_roots, settings.max_file_bytes)
        service = DocumentService(
            policy,
            max_output_chars=settings.max_output_chars,
            ollama_url=settings.ollama_url,
            tesseract_command=settings.tesseract_command,
        )
        registry.extend(DocumentProvider(service).specs())

    return Runtime(registry=registry, clients=clients)


async def run() -> None:
    settings = Settings.from_env()
    runtime = build_runtime(settings)
    server = Server(f"bosscore-{settings.profile}")

    @server.list_tools()
    async def list_tools():
        return runtime.registry.list_tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None):
        try:
            result = await runtime.registry.call(name, arguments)
            return success(result)
        except Exception as exc:
            return failure(exc)

    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        await runtime.close()


def cli() -> None:
    asyncio.run(run())

