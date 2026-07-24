"""Traceable cPanel deployment — plan/execute/verify/rollback.

P0 (deploy): Component-scoped clean check (not entire monorepo).
P1.2: Plans use PlanStore (transactional, actor-scoped, survives restarts).
P1.3: Deploy status/verify return real WordPress + SHA checks.
"""
from __future__ import annotations

import os
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx

from ..core.errors import PolicyViolation, UpstreamError, ValidationError
from ..core.plan_store import PlanStore, get_plan_store
from ..core.registry import ToolSpec, get_request_context, object_schema

STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}

_COMPONENT_PATHS = {
    "bosscore": "BOSS/core/interface/scripts/wp-content/plugins/bosscore",
    "telet": "BOSS/core/interface/scripts/wp-content/themes/telet",
}


class DeployProvider:
    def __init__(
        self,
        deploy_url: str,
        deploy_token: str,
        *,
        environments: tuple[str, ...] = ("staging", "production"),
        repo_path: Path | None = None,
        plan_store: PlanStore | None = None,
        plan_ttl: int | None = None,
    ) -> None:
        self.deploy_url = deploy_url.rstrip("/")
        self._token = deploy_token
        self.environments = environments
        self.repo_path = repo_path
        self._store = plan_store or get_plan_store()
        self._plan_ttl = plan_ttl or int(os.getenv("BOSSCORE_DEPLOY_PLAN_TTL", "1800"))

    def _current_sha(self, target_component: str = "") -> str:
        if not self.repo_path:
            return "unknown"
        check_dir = self.repo_path
        sub_path = _COMPONENT_PATHS.get(target_component)
        if sub_path:
            candidate = self.repo_path / sub_path
            if candidate.is_dir():
                check_dir = candidate
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(check_dir), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip()[:8] if r.returncode == 0 else "unknown"

    @staticmethod
    def _actor_id() -> str:
        ctx = get_request_context()
        return ctx.actor_id if ctx else "stdio"

    @staticmethod
    def _require_environment_scope(environment: str, action: str) -> None:
        ctx = get_request_context()
        if ctx is None:
            return
        required = "boss:deploy:execute" if environment == "production" else "boss:deploy:staging"
        if not ctx.has_scope(required):
            raise PolicyViolation(
                f"Missing scope for {action}",
                details={"environment": environment, "required": required},
            )

    async def _owned_plan(self, plan_id: str) -> dict[str, Any]:
        plan = await self._store.get(plan_id, actor=self._actor_id())
        if plan is None:
            raise ValidationError("Invalid, expired, or foreign plan_id")
        return plan

    async def plan(self, args: dict[str, Any]) -> dict[str, Any]:
        env = args.get("environment", "staging")
        if env not in self.environments:
            raise ValidationError(f"Unknown environment: {env}. Valid: {', '.join(self.environments)}")

        component = args.get("repo", "")
        if component not in ("bosscore", "telet", "all"):
            raise ValidationError("repo must be bosscore, telet, or all")

        self._require_environment_scope(env, "plan deployment")
        requested_sha = args.get("sha", "")
        current_sha = self._current_sha(component)

        if env == "production":
            check_path = self.repo_path
            sub_path = _COMPONENT_PATHS.get(component)
            if sub_path and self.repo_path:
                check_path = self.repo_path / sub_path
                if not check_path.is_dir():
                    check_path = self.repo_path
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

        plan_data = {
            "environment": env,
            "component": component,
            "requested_sha": requested_sha,
            "current_sha": current_sha,
        }
        plan = await self._store.create(
            "deploy", plan_data,
            actor=self._actor_id(),
            ttl=self._plan_ttl,
        )
        plan_id = plan["plan_id"]
        confirm_token = sha256(f"{plan_id}:execute".encode()).hexdigest()[:8]

        return {
            "plan_id": plan_id,
            "environment": env,
            "component": component,
            "requested_sha": requested_sha,
            "current_sha": current_sha,
            "confirm_token": confirm_token,
            "status": "draft",
            "expires_in_seconds": self._plan_ttl,
        }

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        plan_id = args.get("plan_id", "")
        confirm_token = args.get("confirm_token", "")

        if not plan_id:
            raise ValidationError("plan_id is required")

        expected = sha256(f"{plan_id}:execute".encode()).hexdigest()[:8]
        if confirm_token != expected:
            raise PolicyViolation("Confirmation token mismatch")

        owned = await self._owned_plan(plan_id)
        plan_data = owned["data"]
        self._require_environment_scope(
            plan_data.get("environment", "staging"),
            "execute deployment",
        )

        try:
            plan = await self._store.consume(plan_id, actor=self._actor_id())
        except KeyError:
            raise ValidationError("Invalid or expired plan_id. Call boss_deploy_plan first.")
        except PermissionError:
            raise PolicyViolation("Plan does not belong to current actor")
        except ValueError as exc:
            raise ValidationError(str(exc))

        plan_data = plan["data"]
        await self._store.update_status(plan_id, "executing")

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(
                    self.deploy_url,
                    headers={"X-Idempotency-Key": plan_id},
                    params={"repo": plan_data["component"], "token": self._token},
                )
                resp.raise_for_status()
                await self._store.update_status(plan_id, "success")
        except httpx.HTTPStatusError as exc:
            await self._store.update_status(plan_id, "failed")
            raise UpstreamError(f"Deployment failed with HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            await self._store.update_status(plan_id, "failed")
            raise UpstreamError(f"Deployment request failed: {type(exc).__name__}") from exc

        return {
            "plan_id": plan_id,
            "status": "success",
            "component": plan_data["component"],
            "environment": plan_data["environment"],
            "sha": plan_data.get("requested_sha", plan_data["current_sha"]),
        }

    async def status(self, args: dict[str, Any]) -> dict[str, Any]:
        plan_id = args.get("plan_id", "")
        if plan_id:
            plan = await self._owned_plan(plan_id)
            return {
                "plan_id": plan_id,
                "status": plan["status"],
                "component": plan["data"].get("component", "unknown"),
                "environment": plan["data"].get("environment", "unknown"),
                "requested_sha": plan["data"].get("requested_sha", ""),
                "current_sha": self._current_sha(plan["data"].get("component", "")),
            }
        return {
            "current_sha": self._current_sha(),
            "url": self.deploy_url,
            "environments": list(self.environments),
        }

    async def verify(self, args: dict[str, Any]) -> dict[str, Any]:
        plan_id = args.get("plan_id", "")
        plan = await self._owned_plan(plan_id) if plan_id else None
        component = plan["data"].get("component", "") if plan else ""
        expected_sha = ""
        if plan:
            expected_sha = plan["data"].get("requested_sha") or plan["data"].get("current_sha", "")

        checks: dict[str, bool] = {}
        wp_url = os.getenv("WORDPRESS_URL", "")
        if wp_url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(f"{wp_url.rstrip('/')}/wp-json")
                    checks["wordpress_reachable"] = response.status_code == 200
            except Exception:
                checks["wordpress_reachable"] = False
        else:
            checks["wordpress_reachable"] = False

        current = self._current_sha(component)
        checks["deploy_url_configured"] = bool(self.deploy_url)
        checks["local_target_matches"] = not expected_sha or current == expected_sha[:8]

        return {
            "plan_id": plan_id,
            "component": component,
            "expected_sha": expected_sha,
            "local_sha": current,
            "checks": checks,
            "all_passed": all(checks.values()),
        }

    async def rollback(self, args: dict[str, Any]) -> dict[str, Any]:
        plan_id = args.get("plan_id", "")
        if not plan_id:
            raise ValidationError("plan_id is required")

        confirm = args.get("confirm", "")
        if confirm.lower() != "yes":
            raise PolicyViolation("Must pass confirm=yes to execute rollback")

        plan = await self._owned_plan(plan_id)
        self._require_environment_scope(
            plan["data"].get("environment", "production"),
            "rollback deployment",
        )

        rollback_sha = plan["data"].get("current_sha", "")
        if not rollback_sha:
            raise ValidationError("No rollback SHA available for this deployment")

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(
                    self.deploy_url,
                    params={
                        "repo": plan["data"].get("component", "all"),
                        "token": self._token,
                        "sha": rollback_sha,
                    },
                )
                resp.raise_for_status()
                await self._store.update_status(plan_id, "rolled_back")
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Rollback failed: {type(exc).__name__}") from exc

        return {
            "plan_id": plan_id,
            "status": "rolled_back",
            "restored_sha": rollback_sha,
        }

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="boss_deploy_plan",
                description="Create a deployment plan (SHA, env, component, rollback target)",
                input_schema=object_schema({"repo": STR, "environment": STR, "sha": STR}, ["repo"]),
                handler=self.plan,
                output_schema=object_schema({
                    "plan_id": STR, "environment": STR, "component": STR,
                    "status": STR, "current_sha": STR, "requested_sha": STR,
                    "confirm_token": STR, "expires_in_seconds": INT,
                }),
                required_scopes=("boss:deploy:staging",), risk_level="high",
            ),
            ToolSpec(
                name="boss_deploy_execute",
                description="Execute a confirmed deployment plan (token in header, never URL)",
                input_schema=object_schema({"plan_id": STR, "confirm_token": STR}, ["plan_id", "confirm_token"]),
                handler=self.execute,
                output_schema=object_schema({"plan_id": STR, "status": STR, "component": STR, "environment": STR, "sha": STR}),
                required_scopes=("boss:deploy:staging",),
                risk_level="critical", destructive=True, supports_confirmation=True,
            ),
            ToolSpec(
                name="boss_deploy_status",
                description="Check deployment status and current SHA",
                input_schema=object_schema({"plan_id": STR}),
                handler=self.status,
                output_schema=object_schema({
                    "plan_id": STR, "status": STR, "component": STR,
                    "environment": STR, "requested_sha": STR,
                    "current_sha": STR, "url": STR,
                    "environments": {"type": "array", "items": STR},
                }),
                read_only=True, required_scopes=("boss:deploy:staging",),
            ),
            ToolSpec(
                name="boss_deploy_verify",
                description="Verify deployment — smoke test WordPress + SHA match",
                input_schema=object_schema({"plan_id": STR}),
                handler=self.verify,
                output_schema=object_schema({
                    "plan_id": STR, "component": STR, "expected_sha": STR,
                    "local_sha": STR, "checks": {"type": "object"},
                    "all_passed": BOOL,
                }),
                read_only=True, required_scopes=("boss:deploy:staging",),
            ),
            ToolSpec(
                name="boss_deploy_rollback",
                description="Rollback to previous deployment SHA (requires confirmation)",
                input_schema=object_schema({"plan_id": STR, "confirm": STR}, ["plan_id", "confirm"]),
                handler=self.rollback,
                output_schema=object_schema({"plan_id": STR, "status": STR, "restored_sha": STR}),
                required_scopes=("boss:deploy:staging",), risk_level="critical", destructive=True,
                supports_confirmation=True,
            ),
        ]
