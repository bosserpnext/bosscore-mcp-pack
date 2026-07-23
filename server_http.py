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
        "scopes_supported": [
            "boss:health", "boss:wp:read", "boss:wp:write",
            "boss:files:read", "boss:git:read", "boss:git:write",
            "boss:deploy:staging",
        ],
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
        "scopes_supported": [
            "boss:health", "boss:wp:read", "boss:wp:write",
            "boss:files:read", "boss:git:read", "boss:git:write",
            "boss:deploy:staging",
        ],
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
    """ASGI middleware: Bearer token validation + Origin check."""

    def __init__(self, app):
        self.app = app
        self.enforce = os.getenv("BOSSCORE_MCP_ENFORCE_AUTH", "").lower() in ("1", "true", "yes")
        self.allowed_origins = get_allowed_origins()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # Origin check (skip OAuth metadata endpoints)
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

        # OAuth endpoints: pass through
        if path.startswith("/.well-known/") or path.startswith("/oauth/"):
            await self.app(scope, receive, send)
            return

        # MCP endpoint: validate Bearer token
        if path.startswith("/sse/"):
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token_str = auth_header[7:].strip()
                access = await _oauth.load_access_token(token_str)
                if access:
                    scope["mcp_actor"] = access.client_id
                    scope["mcp_scopes"] = access.scopes
                    await self.app(scope, receive, send)
                    return
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

        await self.app(scope, receive, send)


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
            Route("/.well-known/oauth-authorization-server", authorization_server_metadata),
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
