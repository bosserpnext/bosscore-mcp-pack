"""Composable MCP tool registry with outputSchema, scopes, and RequestContext enforcement.

P0.3 — ToolRegistry.call() enforces scopes via RequestContext before dispatching.
list_tools() filters results to only tools the caller is authorized to see.
"""
from __future__ import annotations

import contextvars
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from mcp.types import Tool, ToolAnnotations

from .auth import check_scope
from .errors import PolicyViolation, ValidationError

Handler = Callable[[dict[str, Any]], Awaitable[Any]]

# ── Request context propagation (P0.3, P1.1) ────────────────────────────────────
_current_request_context: contextvars.ContextVar[RequestContext | None] = (
    contextvars.ContextVar("mcp_request_context", default=None)
)


def set_request_context(ctx: RequestContext | None) -> None:
    """Set the current request context for scope enforcement and correlation.

    Must be called at the start of each HTTP request (via middleware).
    Stdio mode leaves it unset (None = backward compatible, no enforcement).
    """
    _current_request_context.set(ctx)


def get_request_context() -> RequestContext | None:
    """Get the current request context, or None if not set (stdio mode)."""
    return _current_request_context.get()


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Per-request security context propagated to every tool call.

    P0.3 — Introduced to enforce scope authorization at the registry level.
    P1.1 — request_id propagated for end-to-end correlation.
    """
    request_id: str
    actor_id: str
    tenant_id: str | None = None
    client_id: str | None = None
    granted_scopes: tuple[str, ...] = ()
    auth_strength: str = "none"  # "none", "bearer", "oauth"
    source_ip_hash: str | None = None
    user_agent: str | None = None

    def has_scope(self, scope: str) -> bool:
        return scope in self.granted_scopes

    def has_all_scopes(self, *scopes: str) -> bool:
        return all(s in self.granted_scopes for s in scopes)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler
    output_schema: dict[str, Any] | None = None
    required_scopes: tuple[str, ...] = ()
    risk_level: str = "low"
    supports_confirmation: bool = False
    read_only: bool = False
    destructive: bool = False
    idempotent: bool = False
    open_world: bool = False

    def as_mcp_tool(self) -> Tool:
        tool_kwargs: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": ToolAnnotations(
                readOnlyHint=self.read_only,
                destructiveHint=self.destructive,
                idempotentHint=self.idempotent,
                openWorldHint=self.open_world,
            ),
        }
        if self.output_schema is not None:
            tool_kwargs["outputSchema"] = self.output_schema
        return Tool(**tool_kwargs)


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

    def list_tools(self, context: RequestContext | None = None) -> list[Tool]:
        """List tools, filtered by caller's granted scopes when context is provided.

        P0.3 — Without context (stdio compatibility), returns all tools.
        With context, only returns tools the caller is authorized to invoke.
        """
        if context is None:
            context = get_request_context()
        if context is None:
            return [spec.as_mcp_tool() for spec in self._tools.values()]
        granted = set(context.granted_scopes)
        return [
            spec.as_mcp_tool() for spec in self._tools.values()
            if not spec.required_scopes or all(s in granted for s in spec.required_scopes)
        ]

    async def call(self, name: str, arguments: dict[str, Any] | None,
                   context: RequestContext | None = None) -> Any:
        """Invoke a tool by name. Enforces scope authorization.

        P0.3 — Scope enforcement mandatory when RequestContext is present.
        Without context (stdio), skips enforcement for backward compatibility.
        """
        spec = self._tools.get(name)
        if spec is None:
            raise ValidationError(f"Unknown tool: {name}")

        if context is None:
            context = get_request_context()

        # P0.3: Enforce scopes before dispatching handler
        if context is not None and spec.required_scopes:
            check_scope(spec.required_scopes, context.granted_scopes, enforce=True)

        # P0.5: Block recursive batch calls
        if name == "boss_batch" and context is not None:
            raise PolicyViolation(
                "boss_batch cannot be called recursively. Use direct tool calls.",
                details={"blocked": "recursive_batch"},
            )

        return await spec.handler(arguments or {})

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def tools_by_scope(self, scope: str) -> tuple[str, ...]:
        return tuple(
            name for name, spec in self._tools.items()
            if not spec.required_scopes or scope in spec.required_scopes
        )


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
