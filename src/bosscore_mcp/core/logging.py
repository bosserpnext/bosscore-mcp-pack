"""Structured JSON-line logging with secret redaction."""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

REDACT_FIELDS = frozenset({
    "authorization", "password", "token", "secret", "app_password",
    "deploy_token", "api_key", "cookie", "set-cookie", "base64",
    "access_token", "refresh_token",
})


def _redact_value(key: str, value: Any) -> Any:
    k = key.lower().replace("-", "_")
    if any(s in k for s in REDACT_FIELDS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {kk: _redact_value(kk, vv) for kk, vv in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value("", vv) for vv in value]
    return value


class RedactedFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname.lower(),
            "logger": record.name,
        }
        for attr in ("request_id", "tool", "actor", "scopes", "duration_ms", "status"):
            if hasattr(record, attr):
                base[attr] = getattr(record, attr)

        if record.args and isinstance(record.args, dict):
            sanitized = _redact_value("", record.args)
            if isinstance(sanitized, dict):
                base.update(sanitized)
        else:
            msg = record.getMessage()
            if msg and msg != record.msg:
                base["message"] = msg

        return json.dumps(base, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactedFormatter())
    logging.getLogger("bosscore_mcp").addHandler(handler)
    logging.getLogger("bosscore_mcp").setLevel(getattr(logging, level.upper(), logging.INFO))


_logger = logging.getLogger("bosscore_mcp")


def log_tool_call(request_id: str, tool: str, actor: str = "anonymous", scopes: tuple[str, ...] = ()) -> None:
    _logger.info(
        "tool_call", extra={
            "request_id": request_id, "tool": tool, "actor": actor,
            "scopes": list(scopes), "status": "called",
        },
    )


def log_tool_result(request_id: str, tool: str, duration_ms: float, ok: bool) -> None:
    _logger.info(
        "tool_result", extra={
            "request_id": request_id, "tool": tool,
            "duration_ms": round(duration_ms, 2), "status": "success" if ok else "error",
        },
    )
