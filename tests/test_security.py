from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bosscore_mcp.core.errors import PolicyViolation
from bosscore_mcp.documents.policy import PathPolicy
from bosscore_mcp.wordpress.client import validate_public_http_url
from bosscore_mcp.wordpress.provider import WordPressProvider


class FakeWordPressClient:
    async def request(self, method, path, **kwargs):
        return {"status": "unexpected"}


def test_raw_wordpress_request_rejects_absolute_url():
    provider = WordPressProvider(FakeWordPressClient())
    with pytest.raises(PolicyViolation):
        asyncio.run(
            provider.raw_request(
                {"endpoint": "https://attacker.invalid/collect", "method": "GET"}
            )
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/private",
        "http://localhost/private",
        "http://[::1]/private",
    ],
)
def test_media_source_rejects_local_addresses(url):
    with pytest.raises(PolicyViolation):
        validate_public_http_url(url)


def test_file_policy_resolves_relative_paths_inside_workspace(tmp_path, monkeypatch):
    relative = tmp_path / "relative.txt"
    relative.write_text("safe", encoding="utf-8")
    monkeypatch.setenv("BOSSCORE_WORKSPACE", str(tmp_path))
    policy = PathPolicy((tmp_path,), 1024)
    assert policy.resolve("relative.txt") == relative.resolve()


def test_file_policy_rejects_paths_outside_roots(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    policy = PathPolicy((allowed,), 1024)
    with pytest.raises(PolicyViolation):
        policy.resolve(str(outside))


def test_file_policy_rejects_credentials_directory(tmp_path):
    protected = tmp_path / "credentials"
    protected.mkdir()
    secret = protected / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    policy = PathPolicy((tmp_path,), 1024)
    with pytest.raises(PolicyViolation):
        policy.resolve(str(secret))


def test_file_policy_rejects_agent_zip_directory(tmp_path):
    protected = tmp_path / "_" / "zip"
    protected.mkdir(parents=True)
    secret = protected / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    policy = PathPolicy((tmp_path,), 1024)
    with pytest.raises(PolicyViolation):
        policy.resolve(str(secret))


def test_file_policy_rejects_oversized_files(tmp_path):
    large = tmp_path / "large.bin"
    large.write_bytes(b"x" * 11)
    policy = PathPolicy((tmp_path,), 10)
    with pytest.raises(PolicyViolation):
        policy.resolve(str(large))
