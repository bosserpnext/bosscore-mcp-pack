"""Hardened asynchronous WordPress REST client."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

from ..core.errors import PolicyViolation, UpstreamError, ValidationError


def _is_forbidden_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def validate_public_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValidationError("source_url must be an HTTP(S) URL")
    if parsed.username or parsed.password:
        raise PolicyViolation("Credentials in source_url are forbidden")
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as exc:
        raise ValidationError(f"Cannot resolve source_url host: {parsed.hostname}") from exc
    if not addresses or any(_is_forbidden_ip(address) for address in addresses):
        raise PolicyViolation(
            "source_url resolves to a private, local, or reserved address"
        )
    return url


class WordPressClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        timeout: float = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=(username, password),
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "bosscore-mcp-pack/0.1"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(self, method: str, path: str, **kwargs):
        if not path.startswith("/") or path.startswith("//"):
            raise PolicyViolation("WordPress requests must use a relative absolute path")
        parsed = urlparse(path)
        if parsed.scheme or parsed.netloc:
            raise PolicyViolation("Absolute URLs are forbidden for authenticated requests")
        try:
            response = await self._client.request(method.upper(), path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise UpstreamError(
                f"WordPress returned HTTP {exc.response.status_code}",
                details={
                    "status": exc.response.status_code,
                    "path": path,
                    "body": exc.response.text[:1000],
                },
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(
                f"WordPress request failed: {exc}",
                details={"path": path},
            ) from exc
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "body": response.text[:5000],
            }

    async def download_public(
        self,
        url: str,
        *,
        max_bytes: int = 25 * 1024 * 1024,
        max_redirects: int = 3,
    ) -> tuple[bytes, str, str]:
        current = validate_public_http_url(url)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30),
            follow_redirects=False,
            headers={"User-Agent": "bosscore-mcp-pack/0.1"},
        ) as client:
            for _ in range(max_redirects + 1):
                async with client.stream("GET", current) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise UpstreamError("Media redirect has no Location header")
                        current = validate_public_http_url(urljoin(current, location))
                        continue
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        raise UpstreamError(
                            f"Media source returned HTTP {exc.response.status_code}"
                        ) from exc
                    declared = response.headers.get("content-length")
                    if declared and int(declared) > max_bytes:
                        raise PolicyViolation("Remote media exceeds the size limit")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise PolicyViolation("Remote media exceeds the size limit")
                        chunks.append(chunk)
                    return (
                        b"".join(chunks),
                        response.headers.get("content-type", "application/octet-stream"),
                        current,
                    )
        raise PolicyViolation("Too many redirects while downloading media")

