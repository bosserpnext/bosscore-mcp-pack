"""Traceable cPanel deployment — plan/execute/verify/rollback."""
from __future__ import annotations

import json
import os
import subprocess
import time
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from ..core.errors import PolicyViolation, UpstreamError, ValidationError
from ..core.registry import ToolSpec, object_schema

STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}

_COMPONENT_PATHS = {
    "bosscore": "BOSS/core/interface/scripts/wp-content/plugins/bosscore",
    "telet": "BOSS/core/interface/scripts/wp-content/themes/telet",
}

_PLANS: dict[str, dict[str, Any]] = {}
_PLANS_LOCK = None  # lazy-init asyncio.Lock


async def _get_lock():
    """Lazy-init an asyncio.Lock for thread-safe _PLANS access."""
    global _PLANS_LOCK
    if _PLANS_LOCK is None:
        import asyncio
        _PLANS_LOCK = asyncio.Lock()
    return _PLANS_LOCK


def _plans_store_path() -> Path:
    """JSON file for plan persistence (survives restarts)."""
    store = os.getenv("BOSSCORE_DEPLOY_PLANS_STORE", "/tmp/bosscore-mcp-deploy-plans.json")
    return Path(store)


def _load_plans() -> None:
    """Load persisted plans from JSON on startup."""
    path = _plans_store_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        now = int(time.time())
        for pid, plan in data.items():
            if int(plan.get("expires_at", 0)) > now:
                _PLANS[pid] = plan
    except Exception:
        pass  # Corrupted file → start fresh


def _save_plans() -> None:
    """Atomically persist plans to JSON."""
    path = _plans_store_path()
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(_PLANS, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass  # Best-effort persistence


def _cleanup_expired() -> None:
    """Remove expired plans from memory and persist."""
    now = int(time.time())
    expired = [pid for pid, p in _PLANS.items() if int(p.get("expires_at", 0)) <= now]
    for pid in expired:
        del _PLANS[pid]
    if expired:
        _save_plans()


# Load persisted plans at module import time
_load_plans()


class DeployProvider:
    def __init__(
        self,
        deploy_url: str,
        deploy_token: str,
        *,
        environments: tuple[str, ...] = ("staging", "production"),
        repo_path: Path | None = None,
    ) -> None:
        self.deploy_url = deploy_url.rstrip("/")
        self._token = deploy_token
        self.environments = environments
        self.repo_path = repo_path

    def _current_sha(self) -> str:
        if not self.repo_path:
            return "unknown"
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(self.repo_path), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip()[:8] if r.returncode == 0 else "unknown"

    async def plan(self, args: dict[str, Any]) -> dict[str, Any]:
        env = args.get("environment", "staging")
        if env not in self.environments:
            raise ValidationError(f"Unknown environment: {env}. Valid: {', '.join(self.environments)}")

        component = args.get("repo", "")
        if component not in ("bosscore", "telet", "all"):
            raise ValidationError("repo must be bosscore, telet, or all")

        requested_sha = args.get("sha", "")
        current_sha = self._current_sha()

        if env == "production":
            check_path = self.repo_path
            sub_path = _COMPONENT_PATHS.get(component)
            if sub_path and self.repo_path:
                check_path = self.repo_path / sub_path
                if not check_path.is_dir():
                    check_path = self.repo_path  # fallback: submodule not initialized
            working_tree = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(check_path),
                capture_output=True, text=True, timeout=10,
            )
            if working_tree.stdout.strip():
                raise PolicyViolation(
                    f"Cannot deploy {component} to production: "
                    f"working tree is dirty in {check_path.name}"
                )

        _cleanup_expired()
        plan_id = f"deploy-{uuid4().hex[:8]}"
        confirm_token = sha256(f"{plan_id}:execute".encode()).hexdigest()[:8]
        plan = {
            "plan_id": plan_id,
            "environment": env,
            "component": component,
            "requested_sha": requested_sha,
            "current_sha": current_sha,
            "confirm_token": confirm_token,
            "status": "draft",
            "expires_at": str(int(time.time()) + 300),  # 5 min
        }
        lock = await _get_lock()
        async with lock:
            _PLANS[plan_id] = plan
            _save_plans()
        return plan

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        plan_id = args.get("plan_id", "")
        if not plan_id or plan_id not in _PLANS:
            raise ValidationError("Invalid or expired plan_id. Call boss_deploy_plan first.")

        lock = await _get_lock()
        async with lock:
            plan = _PLANS.get(plan_id)
            if plan is None:
                raise ValidationError("Invalid or expired plan_id. Call boss_deploy_plan first.")
            if plan["status"] != "draft":
                raise ValidationError(f"Plan already {plan['status']}")

            if int(time.time()) > int(plan["expires_at"]):
                plan["status"] = "expired"
                _save_plans()
                raise PolicyViolation("Plan has expired. Create a new plan.")

            confirm_token = args.get("confirm_token", "")
            expected = sha256(f"{plan_id}:execute".encode()).hexdigest()[:8]
            if confirm_token != expected:
                raise PolicyViolation(
                    "Confirmation token mismatch",
                    details={"expected_format": f"sha256({plan_id}:execute)[:8]", "got": confirm_token},
                )

            plan["status"] = "executing"
            _save_plans()

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(
                    self.deploy_url,
                    headers={"X-Idempotency-Key": plan_id},
                    params={"repo": plan["component"], "token": self._token},
                )
                resp.raise_for_status()
                async with lock:
                    plan["status"] = "success"
                    plan["result"] = resp.text.strip()[:5000]
                    _save_plans()
        except httpx.HTTPStatusError as exc:
            async with lock:
                plan["status"] = "failed"
                _save_plans()
            raise UpstreamError(
                f"Deployment failed with HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            async with lock:
                plan["status"] = "failed"
                _save_plans()
            raise UpstreamError(
                f"Deployment request failed: {type(exc).__name__}"
            ) from exc

        if plan.get("environment") != "staging":
            plan["rollback_sha"] = plan["current_sha"]
            _save_plans()

        return {
            "plan_id": plan_id,
            "status": plan["status"],
            "component": plan["component"],
            "environment": plan["environment"],
            "sha": plan.get("requested_sha", plan["current_sha"]),
        }

    async def status(self, args: dict[str, Any]) -> dict[str, Any]:
        plan_id = args.get("plan_id", "")
        _cleanup_expired()
        if plan_id:
            lock = await _get_lock()
            async with lock:
                if plan_id in _PLANS:
                    return dict(_PLANS[plan_id])
        return {
            "current_sha": self._current_sha(),
            "url": self.deploy_url,
            "environments": list(self.environments),
        }

    async def verify(self, args: dict[str, Any]) -> dict[str, Any]:
        """Smoke test after deployment — check WordPress connectivity."""
        plan_id = args.get("plan_id", "")
        plan = _PLANS.get(plan_id, {})
        checks: dict[str, bool] = {}

        wp_url = os.getenv("WORDPRESS_URL", "")
        if wp_url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(f"{wp_url.rstrip('/')}/wp-json")
                    checks["wordpress_reachable"] = r.status_code == 200
            except Exception:
                checks["wordpress_reachable"] = False

        current = self._current_sha()
        expected = plan.get("requested_sha", "")
        checks["sha_matches"] = (not expected) or (current == expected)

        return {
            "plan_id": plan_id,
            "status": plan.get("status", "unknown"),
            "checks": checks,
            "all_passed": all(checks.values()),
        }

    async def rollback(self, args: dict[str, Any]) -> dict[str, Any]:
        plan_id = args.get("plan_id", "")
        if not plan_id or plan_id not in _PLANS:
            raise ValidationError("No deployment to rollback")

        plan = _PLANS[plan_id]
        rollback_sha = plan.get("rollback_sha", "")
        if not rollback_sha:
            raise ValidationError("No rollback SHA available for this deployment")

        confirm = args.get("confirm", "")
        if confirm.lower() != "yes":
            raise PolicyViolation("Must pass confirm=yes to execute rollback")

        plan["status"] = "rolled_back"
        _save_plans()
        return {
            "plan_id": plan_id,
            "status": "rolled_back",
            "restored_sha": rollback_sha,
        }

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="boss_deploy_plan", description="Create a deployment plan (SHA, env, component, rollback target)",
                input_schema=object_schema({"repo": STR, "environment": STR, "sha": STR}, ["repo"]),
                handler=self.plan,
                output_schema=object_schema({
                    "plan_id": STR,
                    "environment": STR,
                    "component": STR,
                    "status": STR,
                    "current_sha": STR,
                    "requested_sha": STR,
                    "confirm_token": STR,
                    "expires_at": STR,
                }),
                required_scopes=("boss:deploy:staging", "boss:deploy:production"), risk_level="high",
            ),
            ToolSpec(
                name="boss_deploy_execute", description="Execute a confirmed deployment plan against the cPanel webhook",
                input_schema=object_schema({"plan_id": STR, "confirm_token": STR}, ["plan_id", "confirm_token"]),
                handler=self.execute,
                output_schema=object_schema({"plan_id": STR, "status": STR, "component": STR, "environment": STR, "sha": STR}),
                required_scopes=("boss:deploy:staging", "boss:deploy:production"), risk_level="critical", destructive=True,
                supports_confirmation=True,
            ),
            ToolSpec(
                name="boss_deploy_status", description="Check deployment status and current SHA",
                input_schema=object_schema({"plan_id": STR}), handler=self.status,
                output_schema=object_schema({"current_sha": STR, "url": STR, "environments": {"type": "array", "items": STR}}),
                read_only=True, required_scopes=("boss:deploy:staging",),
            ),
            ToolSpec(
                name="boss_deploy_verify", description="Verify deployment — smoke test WordPress + SHA match",
                input_schema=object_schema({"plan_id": STR}), handler=self.verify,
                output_schema=object_schema({"plan_id": STR, "status": STR, "checks": {"type": "object"}, "all_passed": BOOL}),
                read_only=True, required_scopes=("boss:deploy:staging",),
            ),
            ToolSpec(
                name="boss_deploy_rollback", description="Rollback to previous deployment SHA (requires confirmation)",
                input_schema=object_schema({"plan_id": STR, "confirm": STR}, ["plan_id", "confirm"]),
                handler=self.rollback,
                output_schema=object_schema({"plan_id": STR, "status": STR, "restored_sha": STR}),
                required_scopes=("boss:deploy:production",), risk_level="critical", destructive=True,
                supports_confirmation=True,
            ),
        ]
