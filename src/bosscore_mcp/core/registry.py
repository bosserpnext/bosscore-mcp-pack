"""Composable MCP tool registry."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from mcp.types import Tool, ToolAnnotations

from .errors import ValidationError

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler
    read_only: bool = False
    destructive: bool = False
    idempotent: bool = False
    open_world: bool = False

    def as_mcp_tool(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema,
            annotations=ToolAnnotations(
                readOnlyHint=self.read_only,
                destructiveHint=self.destructive,
                idempotentHint=self.idempotent,
                openWorldHint=self.open_world,
            ),
        )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValidationError(f"Duplicate tool name: {spec.name}")
        self._tools[spec.name] = spec

    def extend(self, specs: Iterable[ToolSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def list_tools(self) -> list[Tool]:
        return [spec.as_mcp_tool() for spec in self._tools.values()]

    async def call(self, name: str, arguments: dict[str, Any] | None) -> Any:
        spec = self._tools.get(name)
        if spec is None:
            raise ValidationError(f"Unknown tool: {name}")
        return await spec.handler(arguments or {})

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)


def object_schema(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
    *,
    additional_properties: bool = False,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = required
    return schema

