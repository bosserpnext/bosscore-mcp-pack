"""Point d'entree HTTP Streamable -- BOSSCORE MCP PACK avec OAuth 2.1.

Routes:
  /sse/                                    -> MCP Streamable HTTP (protege par Bearer)
  /.well-known/oauth-protected-resource    -> RFC 9728 metadata
  /.well-known/oauth-authorization-server  -> RFC 8414 metadata
  /oauth/authorize                         -> Authorization endpoint
  /oauth/token                             -> Token endpoint
  /oauth/revoke                            -> Revocation endpoint
"""
import argparse
import base64
import hashlib
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import AnyHttpUrl

from src.bosscore_mcp.app import build_server
from src.bosscore_mcp.core.auth import get_allowed_origins, validate_origin
from src.bosscore_mcp.core.logging import setup_logging
from src.bosscore_mcp.core.oauth import BossOAuthProvider
from src.bosscore_mcp.settings import Settings

_oauth = BossOAuthProvider()


async def protected_resource_metadata(request: Request) -> JSONResponse:
    url = os.getenv("BOSSCORE_MCP_SERVER_URL", "https://vps.bosserpnext.com")
    return JSONResponse({
        "resource": url,
        "authorization_servers": [url],
        "scopes_supported": _oauth.scopes,
        "bearer_methods_supported": ["header"],
        "resource_name": "BOSSCORE MCP Pack",
    })


async def authorization_server_metadata(request: Request) -> JSONResponse:
    url = os.getenv("BOSSCORE_MCP_SERVER_URL", "https://vps.bosserpnext.com")
    return JSONResponse({
        "issuer": url,
        "authorization_endpoint": f"{url}/oauth/authorize",
        "token_endpoint": f"{url}/oauth/token",
        "revocation_endpoint": f"{url}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": _oauth.scopes,
    })


async def openid_configuration(request: Request) -> JSONResponse:
    """Minimal OIDC discovery — enough to satisfy ChatGPT's discovery chain.
    Redirects to the OAuth authorization server metadata for actual OAuth 2.1 details.
    """
    url = os.getenv("BOSSCORE_MCP_SERVER_URL", "https://vps.bosserpnext.com")
    return JSONResponse({
        "issuer": url,
        "authorization_endpoint": f"{url}/oauth/authorize",
        "token_endpoint": f"{url}/oauth/token",
        "scopes_supported": _oauth.scopes,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
    })


async def oauth_authorize(request: Request) -> Response:
    """Auto-approve authorization for pre-registered client."""
    from mcp.server.auth.provider import AuthorizationParams
    client_id = request.query_params.get("client_id", "")
    client = await _oauth.get_client(client_id)
    if client is None:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    params = AuthorizationParams(
        state=request.query_params.get("state"),
        scopes=(request.query_params.get("scope", "")).split() if request.query_params.get("scope") else None,
        code_challenge=request.query_params.get("code_challenge", ""),
        redirect_uri=AnyHttpUrl(request.query_params.get("redirect_uri", "http://localhost")),
        redirect_uri_provided_explicitly="redirect_uri" in request.query_params,
    )
    redirect_url = await _oauth.authorize(client, params)
    return Response(status_code=302, headers={"Location": redirect_url})


async def oauth_token(request: Request) -> JSONResponse:
    """Exchange authorization code for tokens, or refresh."""
    body = await request.form()
    grant_type = body.get("grant_type", "")
    client_id = body.get("client_id", "")
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Basic "):
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8", errors="replace")
        client_id, _, __ = decoded.partition(":")
    client = await _oauth.get_client(client_id)
    if client is None:
        return JSONResponse({"error": "invalid_client"}, status_code=401)

    if grant_type == "authorization_code":
        code_str = body.get("code", "")
        code_verifier = body.get("code_verifier", "")
        auth_code = await _oauth.load_authorization_code(client, code_str)
        if auth_code is None:
            return JSONResponse({"error": "invalid_grant", "error_description": "Code invalid or expired"}, status_code=400)
        # Verify PKCE
        expected = hashlib.sha256(code_verifier.encode()).digest()
        expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b"=").decode()
        if expected_b64 != auth_code.code_challenge:
            return JSONResponse({"error": "invalid_grant", "error_description": "PKCE mismatch"}, status_code=400)
        token = await _oauth.exchange_authorization_code(client, auth_code)
        return JSONResponse(token.model_dump())

    elif grant_type == "refresh_token":
        refresh_str = body.get("refresh_token", "")
        rt = await _oauth.load_refresh_token(client, refresh_str)
        if rt is None:
            return JSONResponse({"error": "invalid_grant", "error_description": "Refresh token invalid or expired"}, status_code=400)
        scopes = (body.get("scope", "")).split() if body.get("scope") else []
        token = await _oauth.exchange_refresh_token(client, rt, scopes)
        return JSONResponse(token.model_dump())

    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


async def oauth_revoke(request: Request) -> JSONResponse:
    body = await request.form()
    token_str = body.get("token", "")
    access = await _oauth.load_access_token(token_str)
    if access:
        await _oauth.revoke_token(access)
    return JSONResponse({})


class OAuthBearerMiddleware:
    """ASGI middleware: OAuth, Origin validation and request context propagation.

    Every MCP request receives an actor-scoped RequestContext. The actor ID is
    derived from the OAuth authorization subject when available, otherwise from
    a non-reversible access-token fingerprint. Raw tokens are never logged or
    persisted in plans.
    """

    def __init__(self, app):
        self.app = app
        self.enforce = os.getenv("BOSSCORE_MCP_ENFORCE_AUTH", "").lower() in ("1", "true", "yes")
        self.allowed_origins = get_allowed_origins()

    @staticmethod
    def _actor_id(access, token_str: str) -> str:
        subject = str(getattr(access, "subject", "") or "")
        client_id = str(getattr(access, "client_id", "") or "")
        generic_subjects = {client_id, "boss-client", "chatgpt-boss"}
        source = subject if subject and subject not in generic_subjects else token_str
        prefix = "oauth-subject" if source == subject else "oauth-token"
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}:{digest}"

    @staticmethod
    def _request_context(request: Request, actor_id: str, scopes, auth_strength: str):
        from src.bosscore_mcp.core.registry import RequestContext

        request_id = request.headers.get("X-Request-ID", f"req-{uuid.uuid4().hex[:12]}")
        forwarded = request.headers.get("X-Forwarded-For", "")
        client_ip = forwarded.split(",")[0].strip()
        if not client_ip and request.client:
            client_ip = request.client.host
        source_ip_hash = (
            hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:12]
            if client_ip else None
        )
        return RequestContext(
            request_id=request_id,
            actor_id=actor_id,
            client_id=actor_id,
            granted_scopes=tuple(scopes),
            auth_strength=auth_strength,
            source_ip_hash=source_ip_hash,
            user_agent=request.headers.get("user-agent", ""),
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").decode("latin-1", errors="replace")
        if scope["path"].startswith("/sse") and "octet-stream" in content_type.lower():
            scope["headers"] = [
                (key, b"application/json" if key == b"content-type" else value)
                for key, value in scope.get("headers", [])
            ]

        request = Request(scope, receive)
        path = request.url.path

        if not path.startswith("/.well-known/") and not path.startswith("/oauth/"):
            origin = request.headers.get("origin")
            try:
                validate_origin(origin, self.allowed_origins)
            except Exception as exc:
                resp = JSONResponse(
                    {"error": {"code": "policy_violation", "message": str(exc)}},
                    status_code=403,
                )
                await resp(scope, receive, send)
                return

        if path.startswith("/.well-known/") or path.startswith("/oauth/"):
            await self.app(scope, receive, send)
            return

        actor_id = "anonymous"
        granted_scopes = ()
        auth_strength = "none"

        if path.startswith("/sse/"):
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token_str = auth_header[7:].strip()
                access = await _oauth.load_access_token(token_str)
                if access:
                    actor_id = self._actor_id(access, token_str)
                    granted_scopes = tuple(access.scopes)
                    auth_strength = "oauth"
                    scope["mcp_actor"] = actor_id
                    scope["mcp_scopes"] = granted_scopes
                elif self.enforce:
                    resp = JSONResponse(
                       {"error": "invalid_token"},
                       status_code=401,
                       headers={"WWW-Authenticate": "Bearer"},
                    )
                    await resp(scope, receive, send)
                    return
            elif self.enforce:
                resp = JSONResponse(
                    {"error": "missing_authorization"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await resp(scope, receive, send)
                return

        from src.bosscore_mcp.core.registry import reset_request_context, set_request_context

        context = self._request_context(request, actor_id, granted_scopes, auth_strength)
        reset_token = set_request_context(context)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_request_context(reset_token)


class MCPEndpoint:
    def __init__(self, sm):
        self._sm = sm

    async def __call__(self, scope, receive, send):
        await self._sm.handle_request(scope, receive, send)


def main():
    parser = argparse.ArgumentParser(description="BOSSCORE MCP -- Streamable HTTP + OAuth 2.1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--profile", default=os.getenv("BOSSCORE_MCP_PROFILE", "wordpress"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    os.environ["BOSSCORE_MCP_PROFILE"] = args.profile
    setup_logging(args.log_level)

    settings = Settings.from_env()
    server = build_server(settings)
    session_manager = StreamableHTTPSessionManager(app=server, stateless=True)

    app = Starlette(
        routes=[
            Mount("/sse/", app=MCPEndpoint(session_manager)),
            Route("/.well-known/oauth-protected-resource", protected_resource_metadata),
            # P0: ChatGPT tries /.well-known/oauth-protected-resource/sse and
            #     /.well-known/oauth-protected-resource/mcp/sse for sub-path discovery.
            #     Catch-all returns the same resource metadata regardless of sub-path.
            Route("/.well-known/oauth-protected-resource/{path:path}", protected_resource_metadata),
            Route("/.well-known/oauth-authorization-server", authorization_server_metadata),
            Route("/.well-known/oauth-authorization-server/{path:path}", authorization_server_metadata),
            Route("/.well-known/openid-configuration", openid_configuration),
            Route("/.well-known/openid-configuration/{path:path}", openid_configuration),
            Route("/oauth/authorize", oauth_authorize),
            Route("/oauth/token", oauth_token, methods=["POST"]),
            Route("/oauth/revoke", oauth_revoke, methods=["POST"]),
        ],
        lifespan=lambda app: session_manager.run(),
    )

    wrapped = OAuthBearerMiddleware(app)

    import uvicorn
    uvicorn.run(wrapped, host=args.host, port=args.port, log_level=args.log_level.lower())


if __name__ == "__main__":
    main()
