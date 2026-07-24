from __future__ import annotations

import asyncio
from contextlib import contextmanager

import httpx
import pytest

import bosscore_mcp.deploy as deploy_module
from bosscore_mcp.core.errors import PolicyViolation, UpstreamError, ValidationError
from bosscore_mcp.core.plan_store import PlanStore
from bosscore_mcp.core.registry import RequestContext, reset_request_context, set_request_context
from bosscore_mcp.deploy import DeployProvider


class FakeAsyncClient:
    def __init__(self, captured: dict, status_code: int = 200, timeout: int = 120):
        self.captured = captured
        self.status_code = status_code
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, **kwargs):
        request_data = {
            "url": url,
            "params": kwargs.get("params", {}),
            "headers": kwargs.get("headers", {}),
        }
        self.captured.setdefault("requests", []).append(request_data)
        request = httpx.Request("GET", url, params=request_data["params"])
        return httpx.Response(
            self.status_code,
            request=request,
            text="ok" if self.status_code == 200 else "denied",
        )


@contextmanager
def actor_context(actor_id: str):
    context = RequestContext(
        request_id=f"request-{actor_id}",
        actor_id=actor_id,
        granted_scopes=("boss:deploy:staging",),
        auth_strength="oauth",
    )
    token = set_request_context(context)
    try:
        yield
    finally:
        reset_request_context(token)


def provider_for(store_file, captured, *, status_code=200):
    store = PlanStore(store_file)
    return DeployProvider(
        "https://example.test/deploy.php",
        "super-secret-token",
        environments=("staging",),
        plan_store=store,
        plan_ttl=1800,
    )


def install_fake_client(monkeypatch, captured, *, status_code=200):
    monkeypatch.setattr(
        deploy_module.httpx,
        "AsyncClient",
        lambda timeout: FakeAsyncClient(
            captured,
            status_code=status_code,
            timeout=timeout,
        ),
    )


def test_plan_survives_provider_restart_and_completes_cycle(monkeypatch, tmp_path):
    captured: dict = {}
    install_fake_client(monkeypatch, captured)
    monkeypatch.setenv("WORDPRESS_URL", "https://wordpress.example.test")
    store_file = tmp_path / "deploy-plans.json"

    async def scenario():
        with actor_context("agent-alpha"):
            first_provider = provider_for(store_file, captured)
            plan = await first_provider.plan(
                {"repo": "bosscore", "environment": "staging"}
            )

        # New provider and new PlanStore instance simulate an MCP process restart.
        with actor_context("agent-alpha"):
            restarted_provider = provider_for(store_file, captured)
            status_before = await restarted_provider.status(
                {"plan_id": plan["plan_id"]}
            )
            executed = await restarted_provider.execute(
                {
                    "plan_id": plan["plan_id"],
                    "confirm_token": plan["confirm_token"],
                }
            )
            verified = await restarted_provider.verify(
                {"plan_id": plan["plan_id"]}
            )
        return plan, status_before, executed, verified

    plan, status_before, executed, verified = asyncio.run(scenario())

    assert plan["status"] == "draft"
    assert plan["expires_in_seconds"] == 1800
    assert status_before["status"] == "draft"
    assert executed["status"] == "success"
    assert verified["component"] == "bosscore"
    assert verified["checks"]["wordpress_reachable"] is True
    assert verified["checks"]["local_target_matches"] is True
    assert store_file.exists()

    deploy_request = captured["requests"][0]
    assert deploy_request["url"] == "https://example.test/deploy.php"
    assert deploy_request["params"] == {
        "repo": "bosscore",
        "token": "super-secret-token",
    }
    assert "Authorization" not in deploy_request["headers"]
    assert deploy_request["headers"]["X-Idempotency-Key"] == plan["plan_id"]


def test_two_agents_own_separate_plans_and_cannot_cross_access(monkeypatch, tmp_path):
    captured: dict = {}
    install_fake_client(monkeypatch, captured)
    store_file = tmp_path / "deploy-plans.json"
    provider = provider_for(store_file, captured)

    async def scenario():
        with actor_context("agent-alpha"):
            alpha = await provider.plan(
                {"repo": "bosscore", "environment": "staging"}
            )
        with actor_context("agent-beta"):
            beta = await provider.plan(
                {"repo": "telet", "environment": "staging"}
            )
            beta_status = await provider.status({"plan_id": beta["plan_id"]})
            with pytest.raises(ValidationError):
                await provider.status({"plan_id": alpha["plan_id"]})
            with pytest.raises(ValidationError):
                await provider.execute(
                    {
                        "plan_id": alpha["plan_id"],
                        "confirm_token": alpha["confirm_token"],
                    }
                )
        with actor_context("agent-alpha"):
            alpha_status = await provider.status({"plan_id": alpha["plan_id"]})
        return alpha, beta, alpha_status, beta_status

    alpha, beta, alpha_status, beta_status = asyncio.run(scenario())

    assert alpha["plan_id"] != beta["plan_id"]
    assert alpha_status["component"] == "bosscore"
    assert beta_status["component"] == "telet"


def test_wrong_confirmation_token_does_not_consume_plan(monkeypatch, tmp_path):
    captured: dict = {}
    install_fake_client(monkeypatch, captured)
    provider = provider_for(tmp_path / "deploy-plans.json", captured)

    async def scenario():
        with actor_context("agent-alpha"):
            plan = await provider.plan(
                {"repo": "bosscore", "environment": "staging"}
            )
            with pytest.raises(PolicyViolation):
                await provider.execute(
                    {
                        "plan_id": plan["plan_id"],
                        "confirm_token": "incorrect",
                    }
                )
            status_after = await provider.status({"plan_id": plan["plan_id"]})
        return plan, status_after

    plan, status_after = asyncio.run(scenario())
    assert status_after["status"] == "draft"

    async def execute_valid():
        with actor_context("agent-alpha"):
            return await provider.execute(
                {
                    "plan_id": plan["plan_id"],
                    "confirm_token": plan["confirm_token"],
                }
            )

    assert asyncio.run(execute_valid())["status"] == "success"


def test_http_error_never_exposes_deploy_token(monkeypatch, tmp_path):
    captured: dict = {}
    install_fake_client(monkeypatch, captured, status_code=403)
    token = "never-print-this-token"
    provider = DeployProvider(
        "https://example.test/deploy.php",
        token,
        environments=("staging",),
        plan_store=PlanStore(tmp_path / "deploy-plans.json"),
    )

    async def scenario():
        with actor_context("agent-alpha"):
            plan = await provider.plan(
                {"repo": "bosscore", "environment": "staging"}
            )
            await provider.execute(
                {
                    "plan_id": plan["plan_id"],
                    "confirm_token": plan["confirm_token"],
                }
            )

    with pytest.raises(UpstreamError) as exc_info:
        asyncio.run(scenario())

    assert "HTTP 403" in str(exc_info.value)
    assert token not in str(exc_info.value)
