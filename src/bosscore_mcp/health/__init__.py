"""Health check and diagnostic tools for the BOSS MCP connector."""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any

from ..core.registry import ToolRegistry, ToolSpec, object_schema

STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}


class HealthProvider:
    def __init__(self, *, registry: ToolRegistry, profile: str = "full", sha: str = "unknown", version: str = "0.1.0") -> None:
        self._registry = registry
        self.profile = profile
        self.sha = sha
        self.version = version

    async def health_check(self, args: dict[str, Any]) -> dict[str, Any]:
        checks: dict[str, Any] = {
            "python_version": sys.version.split()[0],
            "platform": platform.system(),
            "package_version": self.version,
            "commit_sha": self.sha,
            "profile": self.profile,
        }

        # WordPress connectivity (no secret exposure)
        wp_url = os.getenv("WORDPRESS_URL", "")
        if wp_url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(f"{wp_url.rstrip('/')}/wp-json")
                    checks["wordpress"] = "reachable" if r.status_code == 200 else f"HTTP {r.status_code}"
            except Exception as exc:
                checks["wordpress"] = f"unreachable: {exc}"

        # File roots check
        roots = os.getenv("BOSSCORE_FILE_ROOTS", "")
        if roots:
            root_list = [r.strip() for r in roots.split(os.pathsep) if r.strip()]
            checks["file_roots"] = {
                "count": len(root_list),
                "accessible": [r for r in root_list if Path(r).is_dir()],
            }

        # Git config check
        workspace = os.getenv("BOSSCORE_WORKSPACE", "")
        if workspace:
            git_dir = Path(workspace) / ".git"
            checks["git_configured"] = git_dir.is_dir()

        # Deploy config check
        checks["deploy_configured"] = bool(os.getenv("DEPLOY_TOKEN", ""))

        return {"status": "healthy", "checks": checks}

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
                name="boss_health_check", description="Check server health — version, WordPress, files, Git, deploy (no secrets)",
                input_schema=object_schema(), handler=self.health_check,
                output_schema=object_schema({"status": STR, "checks": {"type": "object"}}),
                read_only=True, required_scopes=("boss:health",),
            ),
            ToolSpec(
                name="boss_runtime_info", description="Runtime details — version, Python, commit SHA, platform",
                input_schema=object_schema(), handler=self.runtime_info,
                output_schema=object_schema({"version": STR, "commit_sha": STR, "profile": STR, "python": STR}),
                read_only=True, required_scopes=("boss:health",),
            ),
            ToolSpec(
                name="boss_tool_inventory", description="List all loaded tools by name",
                input_schema=object_schema(), handler=self.tool_inventory,
                output_schema=object_schema({"total": INT, "tools": {"type": "array", "items": STR}, "profile": STR}),
                read_only=True, required_scopes=("boss:health",),
            ),
            ToolSpec(
                name="boss_config_check", description="Check environment configuration (secrets redacted)",
                input_schema=object_schema(), handler=self.config_check,
                output_schema=object_schema({"profile": STR, "config": {"type": "object"}}),
                read_only=True, required_scopes=("boss:health",),
            ),
        ]
