"""Persistent transactional plan store — replaces in-memory _PLANS globals.

P1.2 — Plans survive restarts, worker changes, and multi-process setups.
Single JSON file per process with atomic writes (write-to-temp, rename).
Owner/actor scoping prevents cross-conversation plan collisions.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

_JSON_LOCK = asyncio.Lock()

# Default store path (survives restarts if on persistent volume)
DEFAULT_STORE_DIR = Path(os.getenv("BOSSCORE_MCP_STORE_DIR", tempfile.gettempdir()))
DEFAULT_STORE_FILE = DEFAULT_STORE_DIR / "bosscore-mcp-plans.json"


class PlanStore:
    """Thread-safe, atomic-write plan store.

    Usage:
        store = PlanStore()
        plan = store.create("exec", {"command": "ls"}, actor="chatgpt")
        store.get(plan["plan_id"], actor="chatgpt")  # scoped
        store.consume(plan["plan_id"], actor="chatgpt")  # one-shot
    """

    def __init__(self, file_path: Path | None = None) -> None:
        self._path = file_path or DEFAULT_STORE_FILE
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, Any]:
        """Read the store (NOT thread-safe — caller must hold lock)."""
        if not self._path.exists():
            return {"version": 1, "plans": {}, "created_at": time.time()}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "plans": {}, "created_at": time.time()}

    def _write_atomic(self, data: dict[str, Any]) -> None:
        """Atomic write via temp file + rename."""
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._path)  # atomic on Linux

    def _cleanup_expired(self, data: dict[str, Any]) -> int:
        """Remove expired plans. Returns count removed."""
        now = int(time.time())
        removed = 0
        expired = [
            pid for pid, p in data.get("plans", {}).items()
            if p.get("expires_at", 0) and now > p["expires_at"]
        ]
        for pid in expired:
            del data["plans"][pid]
            removed += 1
        return removed

    async def create(self, kind: str, data: dict[str, Any], *,
                     actor: str = "unknown",
                     ttl: int = 300,
                     tenant: str | None = None) -> dict[str, Any]:
        """Create a new plan. Returns plan object with plan_id."""
        plan_id = f"{kind}-{hashlib.sha256(os.urandom(16)).hexdigest()[:12]}"
        now = int(time.time())
        plan = {
            "plan_id": plan_id,
            "kind": kind,
            "actor": actor,
            "tenant": tenant,
            "data": data,
            "status": "draft",
            "created_at": now,
            "expires_at": now + ttl,
            "version": 1,
        }

        async with _JSON_LOCK:
            store = self._read()
            self._cleanup_expired(store)
            store["plans"][plan_id] = plan
            self._write_atomic(store)

        return plan

    async def get(self, plan_id: str, *, actor: str | None = None) -> dict[str, Any] | None:
        """Get a plan. If actor specified, only returns plan owned by that actor."""
        async with _JSON_LOCK:
            store = self._read()
            self._cleanup_expired(store)
            plan = store.get("plans", {}).get(plan_id)
            if plan is None:
                return None
            if actor is not None and plan.get("actor") != actor:
                return None  # cross-actor access denied
            return dict(plan)

    async def consume(self, plan_id: str, *, actor: str) -> dict[str, Any]:
        """Get a plan and mark it as consumed (one-shot execution).

        Returns the plan data or raises KeyError/ValueError.
        """
        async with _JSON_LOCK:
            store = self._read()
            self._cleanup_expired(store)
            plan = store.get("plans", {}).get(plan_id)
            if plan is None:
                raise KeyError(f"Plan {plan_id} not found or expired")
            if plan.get("actor") != actor:
                raise PermissionError(f"Plan {plan_id} owned by {plan.get('actor')}, not {actor}")
            if plan["status"] != "draft":
                raise ValueError(f"Plan {plan_id} already {plan['status']}")
            plan["status"] = "consumed"
            plan["consumed_at"] = int(time.time())
            self._write_atomic(store)
            return dict(plan)

    async def update_status(self, plan_id: str, status: str) -> None:
        """Update plan status only."""
        async with _JSON_LOCK:
            store = self._read()
            plan = store.get("plans", {}).get(plan_id)
            if plan is None:
                return
            plan["status"] = status
            plan["updated_at"] = int(time.time())
            self._write_atomic(store)

    async def list_by_actor(self, actor: str, *, kind: str | None = None) -> list[dict[str, Any]]:
        """List active plans for an actor."""
        async with _JSON_LOCK:
            store = self._read()
            self._cleanup_expired(store)
            plans = [
                dict(p) for p in store.get("plans", {}).values()
                if p.get("actor") == actor and p.get("status") == "draft"
            ]
            if kind:
                plans = [p for p in plans if p.get("kind") == kind]
            return plans

    async def stats(self) -> dict[str, Any]:
        """Return store statistics."""
        async with _JSON_LOCK:
            store = self._read()
            plans = store.get("plans", {})
            return {
                "total": len(plans),
                "by_status": {
                    status: sum(1 for p in plans.values() if p.get("status") == status)
                    for status in {"draft", "running", "completed", "error", "expired", "consumed"}
                },
                "file_path": str(self._path),
                "file_size_bytes": self._path.stat().st_size if self._path.exists() else 0,
            }


# Global singleton (lazy init for backward compatibility)
_store: PlanStore | None = None


def get_plan_store() -> PlanStore:
    global _store
    if _store is None:
        _store = PlanStore()
    return _store
