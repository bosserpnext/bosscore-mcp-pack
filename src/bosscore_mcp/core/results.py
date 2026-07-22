"""Consistent MCP result envelopes with structuredContent and isError."""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from mcp.types import CallToolResult, TextContent

from .errors import BosscoreMcpError


def _request_id() -> str:
    return uuid4().hex[:12]


def success(data: Any, *, request_id: str | None = None, duration_ms: int | float = 0, tool: str = "") -> CallToolResult:
    """Build a success CallToolResult with structuredContent and meta.

    Returns both TextContent (for backward compat) and structuredContent
    (for MCP clients that support outputSchema validation).
    """
    req_id = request_id or _request_id()
    meta = {"request_id": req_id, "ok": True, "tool": tool, "duration_ms": round(duration_ms, 2)}
    payload = {"ok": True, "data": data, "meta": meta}
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=payload,
        isError=False,
        meta={"request_id": req_id, "tool": tool},
    )


def failure(error: Exception, *, request_id: str | None = None, tool: str = "") -> CallToolResult:
    """Build a failure CallToolResult with structuredContent and isError=True.

    Distinguishes between BosscoreMcpError (known, safe) and unexpected errors
    (redacted to avoid leaking internals).
    """
    req_id = request_id or _request_id()
    if isinstance(error, BosscoreMcpError):
        err_payload = {"code": error.code, "message": error.message, "details": error.details}
    else:
        err_payload = {
            "code": "internal_error",
            "message": f"{type(error).__name__}: {error}",
            "details": {},
        }
    meta = {"request_id": req_id, "ok": False, "tool": tool}
    payload = {"ok": False, "error": err_payload, "meta": meta}
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=payload,
        isError=True,
        meta={"request_id": req_id, "tool": tool},
    )
