"""Transport security: Origin validation, Bearer token, and scope enforcement."""
from __future__ import annotations

import os
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .errors import PolicyViolation

# ── Origin ───────────────────────────────────────────────────────────────────────
DEFAULT_ALLOWED_ORIGINS = frozenset({
    "https://chatgpt.com",
    "https://chat.openai.com",
    "https://vps.bosserpnext.com",
    "https://core.bosserpnext.com",
})


def _parse_origin_comma(value: str) -> frozenset[str]:
    return frozenset(o.strip().rstrip("/") for o in value.split(",") if o.strip())


def get_allowed_origins() -> frozenset[str]:
    raw = os.getenv("BOSSCORE_MCP_ALLOWED_ORIGINS", "")
    if not raw:
        return DEFAULT_ALLOWED_ORIGINS
    return _parse_origin_comma(raw)


def validate_origin(origin: str | None, allowed: frozenset[str]) -> None:
    if origin is None:
        return  # Allow when absent (some MCP clients don't send Origin)
    parsed = origin.rstrip("/").lower()
    if parsed not in {o.lower() for o in allowed}:
        raise PolicyViolation("Origin not allowed", details={"origin": origin})


# ── Bearer token ─────────────────────────────────────────────────────────────────
def _parse_tokens_comma(value: str) -> dict[str, dict[str, Any]]:
    tokens: dict[str, dict[str, Any]] = {}
    for entry in value.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        token, rest = entry.split(":", 1)
        parts = rest.split("|")
        tokens[token.strip()] = {
            "actor": parts[0].strip() if parts else "client",
            "scopes": tuple(p.strip() for p in parts[1].split("+")) if len(parts) > 1 and parts[1] else (),
        }
    return tokens


def validate_token(auth_header: str | None, valid_tokens: dict[str, dict[str, Any]], enforce: bool) -> dict[str, Any]:
    """Validate Bearer token. Fail-closed: refuse all requests if enforce=True and no tokens configured.

    P0.2 — Previously returned anonymous when valid_tokens was empty, allowing
    a misconfigured server to accept any request. Now raises PolicyViolation.
    """
    if enforce and not valid_tokens:
        raise PolicyViolation(
            "Authentication required but no tokens configured. "
            "Set BOSSCORE_MCP_TOKENS or disable BOSSCORE_MCP_ENFORCE_AUTH."
        )

    if not valid_tokens:
        return {"actor": "anonymous", "scopes": ()}

    if not auth_header:
        if enforce:
            raise PolicyViolation("Missing Authorization header", details={"required": True})
        return {"actor": "anonymous", "scopes": ()}

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        if enforce:
            raise PolicyViolation("Authorization must be Bearer <token>")
        return {"actor": "anonymous", "scopes": ()}

    token_info = valid_tokens.get(token.strip())
    if not token_info:
        if enforce:
            raise PolicyViolation("Invalid token")
        return {"actor": "anonymous", "scopes": ()}

    return token_info


def check_scope(required_scopes: tuple[str, ...], granted_scopes: tuple[str, ...], enforce: bool) -> None:
    if not required_scopes:
        return
    granted = set(granted_scopes)
    if not all(s in granted for s in required_scopes):
        if enforce:
            missing = [s for s in required_scopes if s not in granted]
            raise PolicyViolation(
                "Insufficient scopes",
                details={"required": list(required_scopes), "granted": list(granted_scopes), "missing": missing},
            )


# ── Starlette middleware ─────────────────────────────────────────────────────────
class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, env_prefix: str = "BOSSCORE_MCP") -> None:
        super().__init__(app)
        self.allowed_origins = get_allowed_origins()
        tokens_raw = os.getenv(f"{env_prefix}_TOKENS", "")
        self.valid_tokens = _parse_tokens_comma(tokens_raw)
        self.enforce = os.getenv(f"{env_prefix}_ENFORCE_AUTH", "").lower() in ("1", "true", "yes")

        # P0.2: Fail startup if auth is enforced but no tokens configured
        if self.enforce and not self.valid_tokens:
            raise RuntimeError(
                "BOSSCORE_MCP_ENFORCE_AUTH=true but BOSSCORE_MCP_TOKENS is empty. "
                "Refusing to start with security gap."
            )

    async def dispatch(self, request: Request, call_next):
        try:
            origin = request.headers.get("origin")
            validate_origin(origin, self.allowed_origins)

            auth = request.headers.get("authorization")
            token_info = validate_token(auth, self.valid_tokens, self.enforce)
            request.state.mcp_actor = token_info["actor"]
            request.state.mcp_scopes = token_info["scopes"]
            request.state.mcp_enforce_auth = self.enforce

            # P0.3 / P1.1: Build RequestContext for scope enforcement and correlation
            from .registry import RequestContext, set_request_context

            import hashlib
            import time
            from uuid import uuid4

            request_id = request.headers.get("X-Request-ID", f"req-{uuid4().hex[:12]}")
            client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            source_ip_hash = (
                hashlib.sha256(client_ip.encode()).hexdigest()[:12]
                if client_ip else None
            )

            ctx = RequestContext(
                request_id=request_id,
                actor_id=token_info["actor"],
                granted_scopes=token_info["scopes"],
                auth_strength="bearer" if token_info["actor"] != "anonymous" else "none",
                source_ip_hash=source_ip_hash,
                user_agent=request.headers.get("user-agent", ""),
            )
            set_request_context(ctx)

            response = await call_next(request)
        except PolicyViolation as exc:
            msg = exc.message.lower()
            status = 403 if ("origin" in msg or "scope" in msg) else 401
            return JSONResponse(
                {"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
                status_code=status,
            )
        return response
