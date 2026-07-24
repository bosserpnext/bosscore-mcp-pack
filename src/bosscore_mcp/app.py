"""Unified MCP runtime — single composition for all transports (stdio + HTTP).

Replaces the split-brain: server.py and server_http.py both delegate here.

P0.3 — RequestContext propagated through list_tools/call_tool for scope enforcement.
P0.4 — Capability profiles: Public (read-only), Workspace (tenant-bound), Operator (full).
P1.1 — Request ID correlation propagated end-to-end.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from mcp.server import Server

from .core.errors import BosscoreMcpError
from .core.logging import log_tool_call, log_tool_result
from .core.registry import ToolRegistry, get_request_context
from .core.results import failure, success
from .deploy import DeployProvider
from .documents.policy import PathPolicy
from .documents.provider import DocumentProvider
from .documents.service import DocumentService
from .exec import ExecProvider
from .git import GitProvider
from .health import HealthProvider
from .settings import Settings
from .wordpress.client import WordPressClient
from .wordpress.provider import WordPressProvider

_BASE = Path(__file__).resolve().parent.parent.parent


def _git_sha() -> str:
    try:
        import subprocess
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(_BASE), timeout=5,
        )
        return r.stdout.strip()[:8] if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _package_version() -> str:
    try:
        from importlib.metadata import version
        return version("bosscore-mcp-pack")
    except Exception:
        return "0.1.0"


def build_runtime(settings: Settings) -> tuple[ToolRegistry, list]:
    """Build the unified tool registry with all providers.

    P0.4 — Capability profiles determine which tools are registered:
      - public:     WordPress read-only + health (no Exec, Git write, Deploy)
      - workspace:  WordPress read/write + documents + health + Git read
      - operator:   Full (Exec, Git write, Deploy) — private network only

    Returns (registry, list of async_close callbacks).
    """
    registry = ToolRegistry()
    cleanups: list = []

    workspace = Path(os.getenv("BOSSCORE_WORKSPACE", ""))
    has_workspace = bool(workspace and workspace.is_dir())
    profile = settings.profile  # "public", "workspace", "full" → operator

    # ── WordPress ────────────────────────────────────────────────────────────
    if settings.profile in {"wordpress", "full", "public", "workspace"}:
        settings.require_wordpress()
        wp_client = WordPressClient(
            settings.wordpress_url,
            settings.wordpress_username,
            settings.wordpress_password,
        )
        cleanups.append(wp_client.close)
        registry.extend(WordPressProvider(wp_client).specs())

    # ── Documents ────────────────────────────────────────────────────────────
    if settings.profile in {"files", "full", "workspace"}:
        settings.require_file_roots()
        policy = PathPolicy(settings.file_roots, settings.max_file_bytes)
        doc_service = DocumentService(
            policy,
            max_output_chars=settings.max_output_chars,
            ollama_url=settings.ollama_url,
            tesseract_command=settings.tesseract_command,
        )
        registry.extend(DocumentProvider(doc_service).specs())

    # ── Git (read-only for workspace, full for operator) ─────────────────────
    if has_workspace and profile in {"full", "workspace"}:
        try:
            git_provider = GitProvider(
                workspace,
                branch=os.getenv("BOSSCORE_GIT_BRANCH", "master"),
                remote=os.getenv("BOSSCORE_GIT_REMOTE", "origin"),
                allowlist=(str(workspace),),
            )
            registry.extend(git_provider.specs())
        except Exception:
            pass

    # ── Deploy (operator only) ───────────────────────────────────────────────
    deploy_token = os.getenv("DEPLOY_TOKEN", "")
    deploy_url = os.getenv("DEPLOY_URL", "https://core.bosserpnext.com/deploy.php")
    if deploy_token and (profile == "full" or profile == "operator"):
        deploy_provider = DeployProvider(
            deploy_url, deploy_token,
            repo_path=workspace if has_workspace else None,
        )
        registry.extend(deploy_provider.specs())

    # ── Health ───────────────────────────────────────────────────────────────
    health = HealthProvider(
        registry=registry,
        profile=profile,
        sha=_git_sha(),
        version=_package_version(),
    )
    registry.extend(health.specs())

    # ── Exec (operator only — P0.4: removed from public/workspace) ───────────
    if has_workspace and profile == "full":
        exec_provider = ExecProvider()
        registry.extend(exec_provider.specs())

    # ── Batch (P0.5: read-only guardrails applied in BatchProvider) ──────────
    from .batch import BatchProvider
    registry.extend(BatchProvider(registry=registry).specs())

    # ── Coordination (PACTE-BOSS) — workspace+ profiles ────────────────────────
    if profile in {"full", "workspace"}:
        try:
            from .coordination import CoordinationProvider
            registry.extend(CoordinationProvider().specs())
        except Exception:
            pass

    return registry, cleanups


def build_server(settings: Settings) -> Server:
    """Build and wire the MCP Server with all tools."""
    registry, _cleanups = build_runtime(settings)

    pkg_version = _package_version()
    server = Server(
        name="bosscore-mcp-pack",
        version=pkg_version,
        website_url="https://bomoja.com",
        instructions=(
            "Plateforme SaaS multi-tenant — portail self-service, catalogue de services, "
            "équipe, tickets, facturation, notifications, site web public. "
            "Pipeline de développement full-stack autonome : contenu (WordPress), "
            "versionnement (Git), déploiement (cPanel), shell sandboxé, monitoring. "
            "74 capacités. Par BOSS — Bomoja Tech and Industry Optimal Solutions."
        ),
    )

    @server.list_tools()
    async def list_tools():
        # P0.3: filter tools by caller's scopes when context available
        ctx = get_request_context()
        return registry.list_tools(context=ctx)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None):
        # P1.1: propagate request_id for correlation
        ctx = get_request_context()
        req_id = ctx.request_id if ctx else ""

        t0 = time.perf_counter()
        log_tool_call(req_id, name)
        try:
            result = await registry.call(name, arguments, context=ctx)
            elapsed = (time.perf_counter() - t0) * 1000
            log_tool_result(req_id, name, elapsed, ok=True)
            return success(result, duration_ms=elapsed, tool=name)
        except BosscoreMcpError as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            log_tool_result(req_id, name, elapsed, ok=False)
            return failure(exc, tool=name)
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            log_tool_result(req_id, name, elapsed, ok=False)
            return failure(exc, tool=name)

    return server
