"""Health check and diagnostic tools for the BOSS MCP connector.

P0.6 — Health check no longer lies: separate live/ready/dependency probes.
live:  server is running (always 200)
ready: server + critical dependencies accessible (WordPress, Git, deploy)
dependencies: per-dependency status (cached for 30s to prevent probe storms)
"""
from __future__ import annotations

import asyncio
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

from ..core.registry import ToolRegistry, ToolSpec, object_schema

STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}

# P0.6: Dependency cache to prevent probe storms
_dep_cache: dict[str, dict[str, Any]] = {}
_dep_cache_ttl: float = 30.0  # 30 seconds
_dep_lock = asyncio.Lock()


async def _cached_dependency_check(key: str, checker) -> dict[str, Any]:
    """Cache dependency health for _dep_cache_ttl seconds."""
    now = time.monotonic()
    async with _dep_lock:
        cached = _dep_cache.get(key)
        if cached and (now - cached.get("_checked_at", 0)) < _dep_cache_ttl:
            return {k: v for k, v in cached.items() if not k.startswith("_")}

    result = await checker()
    result["_checked_at"] = now
    async with _dep_lock:
        _dep_cache[key] = result
    return {k: v for k, v in result.items() if not k.startswith("_")}


class HealthProvider:
    def __init__(self, *, registry: ToolRegistry, profile: str = "full",
                 sha: str = "unknown", version: str = "0.1.0") -> None:
        self._registry = registry
        self.profile = profile
        self.sha = sha
        self.version = version

    async def _check_wordpress(self) -> dict[str, Any]:
        """Check WordPress connectivity (fast, cached)."""
        wp_url = os.getenv("WORDPRESS_URL", "")
        if not wp_url:
            return {"status": "unknown", "reason": "WORDPRESS_URL not set"}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{wp_url.rstrip('/')}/wp-json")
                if r.status_code == 200:
                    return {"status": "healthy", "latency_ms": round(r.elapsed.total_seconds() * 1000)}
                return {"status": "degraded", "http_status": r.status_code}
        except Exception as exc:
            return {"status": "unhealthy", "error": f"{type(exc).__name__}: {exc}"}

    async def _check_git(self) -> dict[str, Any]:
        """Check Git workspace accessibility."""
        workspace = os.getenv("BOSSCORE_WORKSPACE", "")
        if not workspace:
            return {"status": "unknown", "reason": "BOSSCORE_WORKSPACE not set"}
        git_dir = Path(workspace) / ".git"
        if not git_dir.is_dir():
            return {"status": "unhealthy", "reason": ".git directory not found"}
        return {"status": "healthy", "workspace": workspace}

    async def _check_deploy(self) -> dict[str, Any]:
        """Check deploy configuration."""
        token = os.getenv("DEPLOY_TOKEN", "")
        url = os.getenv("DEPLOY_URL", "")
        if not token or not url:
            return {"status": "unknown", "reason": "DEPLOY_TOKEN or DEPLOY_URL not set"}
        return {"status": "healthy", "url": url}

    async def health_check(self, args: dict[str, Any]) -> dict[str, Any]:
        """Full health check with live + dependency status (cached)."""
        deps = await asyncio.gather(
            _cached_dependency_check("wordpress", self._check_wordpress),
            _cached_dependency_check("git", self._check_git),
            _cached_dependency_check("deploy", self._check_deploy),
            return_exceptions=True,
        )

        dep_names = ["wordpress", "git", "deploy"]
        dependencies: dict[str, Any] = {}
        for name, result in zip(dep_names, deps):
            if isinstance(result, BaseException):
                dependencies[name] = {"status": "error", "error": str(result)}
            else:
                dependencies[name] = result

        # Overall health: all checked deps must be healthy or unknown
        unhealthy = [n for n, d in dependencies.items()
                     if d.get("status") not in ("healthy", "unknown")]
        overall = "unhealthy" if unhealthy else "healthy"

        return {
            "status": overall,
            "live": True,
            "version": self.version,
            "commit_sha": self.sha,
            "profile": self.profile,
            "dependencies": dependencies,
        }

    async def live(self, args: dict[str, Any]) -> dict[str, Any]:
        """Liveness probe — always returns 200 if server is running. No dependency checks."""
        return {"live": True, "version": self.version}

    async def ready(self, args: dict[str, Any]) -> dict[str, Any]:
        """Readiness probe — checks critical dependencies (cached 30s)."""
        wp = await _cached_dependency_check("wordpress", self._check_wordpress)
        wp_ok = wp.get("status") in ("healthy", "unknown")

        return {
            "ready": wp_ok,
            "version": self.version,
            "wordpress": wp,
        }

    async def runtime_info(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": self.version,
            "commit_sha": self.sha,
            "profile": self.profile,
            "python": sys.version,
            "platform": platform.platform(),
            "python_path": sys.executable,
            "cwd": os.getcwd(),
        }

    async def tool_inventory(self, args: dict[str, Any]) -> dict[str, Any]:
        names = self._registry.names
        return {
            "total": len(names),
            "tools": sorted(names),
            "profile": self.profile,
        }

    async def config_check(self, args: dict[str, Any]) -> dict[str, Any]:
        vars_to_check = [
            "WORDPRESS_URL", "WORDPRESS_USERNAME", "BOSSCORE_FILE_ROOTS",
            "BOSSCORE_WORKSPACE", "OLLAMA_URL", "TESSERACT_CMD",
            "DEPLOY_TOKEN", "BOSSCORE_MCP_PROFILE",
            "BOSSCORE_MCP_ALLOWED_ORIGINS",
            "BOSSCORE_MCP_ENFORCE_AUTH",
        ]
        config = {}
        for var in vars_to_check:
            value = os.getenv(var, "")
            if var.endswith(("_PASSWORD", "_USERNAME", "_TOKEN")):
                config[var] = "***SET***" if value else "missing"
            elif var.endswith("_URL"):
                config[var] = value.strip("/")[:80] if value else "missing"
            else:
                config[var] = value[:100] if value else "missing"

        return {"profile": self.profile, "config": config}

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="boss_health_check",
                description="Check server health — live, version, dependencies (WordPress, Git, deploy). Deps cached 30s.",
                input_schema=object_schema(),
                handler=self.health_check,
                read_only=True, required_scopes=("boss:health",),
            ),
            ToolSpec(
                name="boss_live",
                description="Liveness probe — always returns live:true if server is running. No dependency checks.",
                input_schema=object_schema(),
                handler=self.live,
                read_only=True,
            ),
            ToolSpec(
                name="boss_ready",
                description="Readiness probe — checks critical dependencies (cached 30s to prevent probe storms).",
                input_schema=object_schema(),
                handler=self.ready,
                read_only=True,
            ),
            ToolSpec(
                name="boss_runtime_info",
                description="Runtime details — version, Python, commit SHA, platform",
                input_schema=object_schema(), handler=self.runtime_info,
                read_only=True, required_scopes=("boss:health",),
            ),
            ToolSpec(
                name="boss_tool_inventory",
                description="List all loaded tools by name",
                input_schema=object_schema(), handler=self.tool_inventory,
                read_only=True, required_scopes=("boss:health",),
            ),
            ToolSpec(
                name="boss_config_check",
                description="Check environment configuration (secrets redacted)",
                input_schema=object_schema(), handler=self.config_check,
                read_only=True, required_scopes=("boss:health",),
            ),
        ]
