"""Minimal OAuth 2.1 Authorization Server provider for BOSS MCP.

Serves both as Authorization Server and Resource Server.
Pre-registers a single client (ChatGPT) — no DCR needed.
Tokens are opaque UUIDs, persisted to JSON file to survive restarts.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    OAuthClientInformationFull,
    OAuthToken,
    RefreshToken,
)

# ── Token store ─────────────────────────────────────────────────────────────────
_CODES: dict[str, AuthorizationCode] = {}
_ACCESS_TOKENS: dict[str, AccessToken] = {}
_REFRESH_TOKENS: dict[str, RefreshToken] = {}

_ACCESS_TOKEN_TTL = int(os.getenv("BOSSCORE_MCP_ACCESS_TOKEN_TTL", "86400"))     # 24 hours
_REFRESH_TOKEN_TTL = int(os.getenv("BOSSCORE_MCP_REFRESH_TOKEN_TTL", "604800"))  # 7 days
_AUTH_CODE_TTL = int(os.getenv("BOSSCORE_MCP_AUTH_CODE_TTL", "600"))             # 10 min

_STORE_PATH = Path(os.getenv("BOSSCORE_MCP_OAUTH_STORE",
    "/tmp/bosscore-mcp-oauth-tokens.json"))
_LOCK = Lock()


def _now() -> float:
    return time.time()


def _serialize_token(token: Any) -> dict:
    """Serialize an AccessToken/RefreshToken/AuthorizationCode to a JSON-safe dict."""
    d = {}
    for k, v in token.__dict__.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            d[k] = v
        elif isinstance(v, (list, tuple)):
            d[k] = list(v)
        else:
            d[k] = str(v) if v is not None else None
    return d


def _save() -> None:
    """Persist tokens to JSON file (atomic write)."""
    now = _now()

    def valid(tokens: dict, expiry_attr: str = "expires_at") -> dict:
        return {
            k: _serialize_token(t) for k, t in tokens.items()
            if not getattr(t, expiry_attr, None) or getattr(t, expiry_attr) > now
        }

    data = {
        "access_tokens": valid(_ACCESS_TOKENS),
        "refresh_tokens": valid(_REFRESH_TOKENS, "expires_at"),
        "codes": valid(_CODES),
    }
    tmp = Path(str(_STORE_PATH) + ".tmp")
    with _LOCK:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(_STORE_PATH)


def _load() -> None:
    """Restore tokens from JSON file, skipping expired ones."""
    if not _STORE_PATH.exists():
        return
    try:
        data = json.loads(_STORE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return

    now = _now()

    def _reconstruct(cls, raw: dict, identifier_attr: str = "token") -> Any:
        """Convert a previously‑serialized dict back to an SDK object."""
        expires = raw.get("expires_at", 0)
        # Some objects store `expires_at` as int (seconds), some as float
        if isinstance(expires, (int, float)) and expires <= now:
            return None  # expired — drop it
        obj = cls(
            **{k.replace("resource_server", "resource"): v
               for k, v in raw.items()
               if k in cls.__annotations__}
        )
        return obj

    for raw in data.get("access_tokens", {}).values():
        at = _reconstruct(AccessToken, raw)
        if at:
            _ACCESS_TOKENS[at.token] = at

    for raw in data.get("refresh_tokens", {}).values():
        rt = _reconstruct(RefreshToken, raw)
        if rt:
            _REFRESH_TOKENS[rt.token] = rt

    for raw in data.get("codes", {}).values():
        ac = _reconstruct(AuthorizationCode, raw, "code")
        if ac:
            _CODES[ac.code] = ac


# ── Provider ────────────────────────────────────────────────────────────────────

class BossOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    """Single-client OAuth provider for BOSS MCP.

    Client is pre-registered via environment variables.
    Tokens are opaque (UUID), persisted to JSON file across restarts.
    """

    def __init__(self) -> None:
        self._client_id = os.getenv("BOSSCORE_MCP_OAUTH_CLIENT_ID", "chatgpt-boss")
        self._client_secret = os.getenv("BOSSCORE_MCP_OAUTH_CLIENT_SECRET", "boss-mcp-oauth-secret-change-me")
        self._redirect_uris = [
            u.strip() for u in
            os.getenv("BOSSCORE_MCP_OAUTH_REDIRECT_URIS", "http://localhost,https://chatgpt.com").split(",")
            if u.strip()
        ]
        self._scopes = [
            s.strip() for s in
            os.getenv("BOSSCORE_MCP_OAUTH_SCOPES",
                       "boss:health "
                       "boss:wp:read boss:wp:write "
                       "boss:files:read boss:files:write "
                       "boss:git:read boss:git:write "
                       "boss:deploy:staging boss:deploy:execute "
                       "boss:exec").split()
            if s.strip()
        ]
        self._server_url = os.getenv("BOSSCORE_MCP_SERVER_URL", "https://vps.bosserpnext.com")
        _load()  # Restore tokens from disk

    # ── Client management ───────────────────────────────────────────────────

    @property
    def scopes(self) -> list[str]:
        return list(self._scopes)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if client_id != self._client_id:
            return None
        return OAuthClientInformationFull(
            client_id=self._client_id,
            client_secret=self._client_secret,
            redirect_uris=self._redirect_uris,
            token_endpoint_auth_method="client_secret_basic",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=" ".join(self._scopes),
        )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        raise NotImplementedError("Dynamic client registration is disabled")

    # ── Authorization flow ──────────────────────────────────────────────────

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        code = AuthorizationCode(
            code=uuid.uuid4().hex,
            scopes=params.scopes or self._scopes,
            expires_at=_now() + _AUTH_CODE_TTL,
            client_id=client.client_id or self._client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource or self._server_url,
            subject=client.client_id or "boss-client",
        )
        _CODES[code.code] = code
        _save()

        import urllib.parse
        redirect = str(params.redirect_uri)
        sep = "&" if "?" in redirect else "?"
        state_param = f"&state={params.state}" if params.state else ""
        return f"{redirect}{sep}code={code.code}{state_param}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str,
    ) -> AuthorizationCode | None:
        code = _CODES.get(authorization_code)
        if code is None:
            return None
        if _now() > code.expires_at:
            _CODES.pop(authorization_code, None)
            _save()
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        _CODES.pop(authorization_code.code, None)

        access = AccessToken(
            token=uuid.uuid4().hex,
            client_id=client.client_id or self._client_id,
            scopes=authorization_code.scopes,
            expires_at=int(_now() + _ACCESS_TOKEN_TTL),
            resource=authorization_code.resource,
            subject=authorization_code.subject,
        )
        _ACCESS_TOKENS[access.token] = access

        refresh = RefreshToken(
            token=uuid.uuid4().hex,
            client_id=client.client_id or self._client_id,
            scopes=authorization_code.scopes,
            expires_at=int(_now() + _REFRESH_TOKEN_TTL),
            subject=authorization_code.subject,
        )
        _REFRESH_TOKENS[refresh.token] = refresh
        _save()

        return OAuthToken(
            access_token=access.token,
            token_type="Bearer",
            expires_in=_ACCESS_TOKEN_TTL,
            scope=" ".join(access.scopes),
            refresh_token=refresh.token,
        )

    # ── Token management ────────────────────────────────────────────────────

    async def load_access_token(self, token: str) -> AccessToken | None:
        at = _ACCESS_TOKENS.get(token)
        if at and at.expires_at and _now() > at.expires_at:
            _ACCESS_TOKENS.pop(token, None)
            _save()
            return None
        return at

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str,
    ) -> RefreshToken | None:
        rt = _REFRESH_TOKENS.get(refresh_token)
        if rt is None:
            return None
        if rt.expires_at and _now() > rt.expires_at:
            _REFRESH_TOKENS.pop(refresh_token, None)
            _save()
            return None
        return rt

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        _REFRESH_TOKENS.pop(refresh_token.token, None)

        new_scopes = scopes or refresh_token.scopes
        access = AccessToken(
            token=uuid.uuid4().hex,
            client_id=client.client_id or self._client_id,
            scopes=new_scopes,
            expires_at=int(_now() + _ACCESS_TOKEN_TTL),
            resource=self._server_url,
            subject=refresh_token.subject,
        )
        _ACCESS_TOKENS[access.token] = access

        new_refresh = RefreshToken(
            token=uuid.uuid4().hex,
            client_id=client.client_id or self._client_id,
            scopes=new_scopes,
            expires_at=int(_now() + _REFRESH_TOKEN_TTL),
            subject=refresh_token.subject,
        )
        _REFRESH_TOKENS[new_refresh.token] = new_refresh
        _save()

        return OAuthToken(
            access_token=access.token,
            token_type="Bearer",
            expires_in=_ACCESS_TOKEN_TTL,
            scope=" ".join(new_scopes),
            refresh_token=new_refresh.token,
        )

    async def revoke_token(
        self, token: AccessToken | RefreshToken,
    ) -> None:
        _ACCESS_TOKENS.pop(token.token, None)
        _REFRESH_TOKENS.pop(token.token, None)
        _save()
