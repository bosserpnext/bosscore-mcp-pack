from __future__ import annotations

import asyncio

import httpx
import pytest

import bosscore_mcp.deploy as deploy_module
from bosscore_mcp.core.errors import UpstreamError
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
        self.captured["url"] = url
        self.captured["params"] = kwargs.get("params", {})
        self.captured["headers"] = kwargs.get("headers", {})
        request = httpx.Request("GET", url, params=self.captured["params"])
        return httpx.Response(
            self.status_code,
            request=request,
            text="ok" if self.status_code == 200 else "denied",
        )


def reset_deploy_state(monkeypatch, tmp_path):
    deploy_module._PLANS.clear()
    deploy_module._PLANS_LOCK = None
    monkeypatch.setenv(
        "BOSSCORE_DEPLOY_PLANS_STORE",
        str(tmp_path / "deploy-plans.json"),
    )


def test_plan_and_execute_use_canonical_get_contract(monkeypatch, tmp_path):
    reset_deploy_state(monkeypatch, tmp_path)
    captured: dict = {}
    monkeypatch.setattr(
        deploy_module.httpx,
        "AsyncClient",
        lambda timeout: FakeAsyncClient(captured, timeout=timeout),
    )
    provider = DeployProvider(
        "https://example.test/deploy.php",
        "super-secret-token",
        environments=("staging",),
    )

    async def scenario():
        plan = await provider.plan({"repo": "bosscore", "environment": "staging"})
        result = await provider.execute(
            {
                "plan_id": plan["plan_id"],
                "confirm_token": plan["confirm_token"],
            }
        )
        return plan, result

    plan, result = asyncio.run(scenario())

    assert plan["status"] == "success"
    assert result["status"] == "success"
    assert captured["url"] == "https://example.test/deploy.php"
    assert captured["params"] == {
        "repo": "bosscore",
        "token": "super-secret-token",
    }
    assert "Authorization" not in captured["headers"]
    assert captured["headers"]["X-Idempotency-Key"] == plan["plan_id"]
    assert (tmp_path / "deploy-plans.json").exists()


def test_http_error_never_exposes_deploy_token(monkeypatch, tmp_path):
    reset_deploy_state(monkeypatch, tmp_path)
    captured: dict = {}
    monkeypatch.setattr(
        deploy_module.httpx,
        "AsyncClient",
        lambda timeout: FakeAsyncClient(captured, status_code=403, timeout=timeout),
    )
    token = "never-print-this-token"
    provider = DeployProvider(
        "https://example.test/deploy.php",
        token,
        environments=("staging",),
    )

    async def scenario():
        plan = await provider.plan({"repo": "bosscore", "environment": "staging"})
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
