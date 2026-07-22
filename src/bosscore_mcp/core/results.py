"""Consistent MCP result envelopes."""
from __future__ import annotations

import json
from typing import Any

from mcp.types import TextContent

from .errors import BosscoreMcpError


def success(data: Any) -> list[TextContent]:
    payload = {"ok": True, "data": data}
    return [
        TextContent(
            type="text",
            text=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        )
    ]


def failure(error: Exception) -> list[TextContent]:
    if isinstance(error, BosscoreMcpError):
        payload = {
            "ok": False,
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        }
    else:
        payload = {
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": f"{type(error).__name__}: {error}",
                "details": {},
            },
        }
    return [
        TextContent(
            type="text",
            text=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        )
    ]

