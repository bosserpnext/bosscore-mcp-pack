"""Tests for the PACTE-BOSS coordination store.

Covers: sessions, claims, events, requests, handoffs, snapshots, conflict detection.
Uses an in-memory SQLite database (tmp file).
"""

import os
import tempfile
from pathlib import Path

import pytest

from bosscore_mcp.coordination.store import CoordinationStore


@pytest.fixture
def store():
    """Create a store backed by a temporary file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = CoordinationStore(Path(path))
    yield s
    Path(path).unlink(missing_ok=True)


# ── Sessions ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_and_get_session(store):
    session = await store.register_session(
        "20260724-online-chatgpt-test",
        "ChatGPT", "online", "chatgpt.com",
        task_id="test-1", task_title="Test Session", company="BOSS",
    )
    assert session["session_id"] == "20260724-online-chatgpt-test"
    assert session["agent_name"] == "ChatGPT"
    assert session["status"] == "active"

    got = await store.get_session("20260724-online-chatgpt-test")
    assert got is not None
    assert got["agent_type"] == "online"


@pytest.mark.asyncio
async def test_list_sessions(store):
    await store.register_session("s1", "AgentA", "online", "web", company="BOSS")
    await store.register_session("s2", "AgentB", "local", "opencode", company="CSG")

    all_sessions = await store.list_sessions()
    assert len(all_sessions) == 2

    boss_only = await store.list_sessions(company="BOSS")
    assert len(boss_only) == 1
    assert boss_only[0]["agent_name"] == "AgentA"


@pytest.mark.asyncio
async def test_heartbeat_updates_timestamp(store):
    await store.register_session("s1", "AgentA", "online", "web")
    before = (await store.get_session("s1"))["last_heartbeat_at"]

    import asyncio
    await asyncio.sleep(0.01)

    await store.heartbeat("s1")
    after = (await store.get_session("s1"))["last_heartbeat_at"]
    assert after > before


@pytest.mark.asyncio
async def test_close_session_releases_claims(store):
    await store.register_session("s1", "AgentA", "online", "web")
    await store.create_claim("c1", "s1", "exclusive")
    assert (await store.get_claim("c1"))["status"] == "active"

    await store.close_session("s1")
    assert (await store.get_session("s1"))["status"] == "closed"
    assert (await store.get_claim("c1"))["status"] == "released"


# ── Claims ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_get_claim(store):
    await store.register_session("s1", "AgentA", "online", "web")
    claim = await store.create_claim(
        "c1", "s1", "exclusive",
        task_id="t-1", task_title="My Task",
        repositories=["bosscore"],
        resources=["contract:test", "module:stock:provider"],
        base_shas={"bosscore": "abc123"},
        branch="agent/online-agenta/my-task",
        ttl=7200,
    )
    assert claim["claim_id"] == "c1"
    assert claim["mode"] == "exclusive"
    assert claim["status"] == "active"

    got = await store.get_claim("c1")
    assert got is not None
    assert got["task_title"] == "My Task"


@pytest.mark.asyncio
async def test_list_claims_filtered(store):
    await store.register_session("s1", "A", "online", "web")
    await store.register_session("s2", "B", "local", "opencode")
    await store.create_claim("c1", "s1", "exclusive")
    await store.create_claim("c2", "s2", "observe")

    claims_s1 = await store.list_claims(session_id="s1")
    assert len(claims_s1) == 1

    claims_observe = await store.list_claims(mode="observe")
    assert len(claims_observe) == 1
    assert claims_observe[0]["claim_id"] == "c2"


@pytest.mark.asyncio
async def test_extend_claim(store):
    await store.register_session("s1", "A", "online", "web")
    claim = await store.create_claim("c1", "s1", "exclusive", ttl=3600)

    extended = await store.extend_claim("c1", 7200)
    assert extended["expires_at"] > claim["expires_at"]


@pytest.mark.asyncio
async def test_release_claim(store):
    await store.register_session("s1", "A", "online", "web")
    await store.create_claim("c1", "s1", "exclusive")
    await store.release_claim("c1")
    assert (await store.get_claim("c1"))["status"] == "released"


@pytest.mark.asyncio
async def test_conflict_detection(store):
    await store.register_session("s1", "A", "online", "web")
    await store.register_session("s2", "B", "online", "web")
    await store.create_claim("c1", "s1", "exclusive", resources=["contract:test", "module:stock:provider"])

    # Overlap on contract:test
    conflicts = await store.check_conflicts(["contract:test", "module:sales:provider"])
    assert len(conflicts) == 1
    assert "contract:test" in conflicts[0]["conflicting_resources"]

    # No overlap
    conflicts = await store.check_conflicts(["module:sales:provider"])
    assert len(conflicts) == 0

    # Exclude own claim
    conflicts = await store.check_conflicts(
        ["contract:test"], exclude_claim_id="c1",
    )
    assert len(conflicts) == 0


# ── Events ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_append_and_list_events(store):
    await store.register_session("s1", "A", "online", "web")
    await store.append_event("s1", "session.started")
    await store.append_event("s1", "file.modified", repo="bosscore", path="test.php")

    events = await store.list_events("s1")
    assert len(events) == 2
    assert events[0]["type"] == "session.started"
    assert events[1]["type"] == "file.modified"
    assert events[1]["repo"] == "bosscore"


@pytest.mark.asyncio
async def test_export_journal(store):
    await store.register_session("s1", "ChatGPT", "online", "chatgpt.com",
                                  task_id="t1", task_title="Test")
    await store.append_event("s1", "session.started")
    await store.append_event("s1", "file.modified", path="test.php")
    await store.append_event("s1", "test.passed", summary="42 tests")

    md = await store.export_journal("s1")
    assert "# Journal — s1" in md
    assert "ChatGPT" in md
    assert "session.started" in md
    assert "file.modified" in md
    assert "test.passed" in md
    assert "42 tests" in md


# ── Requests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_requests(store):
    await store.register_session("s1", "A", "online", "web")
    await store.register_session("s2", "B", "online", "web")

    await store.create_request(
        "REQ-001", "s1", "Need transaction events",
        target_scope="module:sales:transaction-events",
        acceptance=["only after commit", "no idempotent replay"],
        priority="high",
    )

    reqs = await store.list_requests(from_session="s1")
    assert len(reqs) == 1
    assert reqs[0]["request_id"] == "REQ-001"
    assert reqs[0]["status"] == "open"


@pytest.mark.asyncio
async def test_accept_and_close_request(store):
    await store.register_session("s1", "A", "online", "web")
    await store.register_session("s2", "B", "online", "web")
    await store.create_request("REQ-001", "s1", "Need something")

    accepted = await store.accept_request("REQ-001", "s2")
    assert accepted["status"] == "accepted"
    assert accepted["target_session"] == "s2"

    closed = await store.close_request("REQ-001", "completed")
    assert closed["status"] == "completed"


# ── Handoffs ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_get_handoff(store):
    await store.register_session("s1", "A", "online", "web")
    result = await store.create_handoff("HOFF-s1", "s1", {
        "mission": {"initial": "Test mission"},
        "work_completed": ["Task 1"],
        "next_safe_action": "Run tests",
    })
    assert result["handoff_id"] == "HOFF-s1"

    session = await store.get_session("s1")
    assert session["status"] == "handoff_pending"

    got = await store.get_handoff("HOFF-s1")
    assert got is not None


@pytest.mark.asyncio
async def test_list_unconsumed_handoffs(store):
    await store.register_session("s1", "A", "online", "web")
    await store.create_handoff("HOFF-s1", "s1", {"test": True})

    unconsumed = await store.list_handoffs(consumed=False)
    assert len(unconsumed) == 1

    consumed = await store.list_handoffs(consumed=True)
    assert len(consumed) == 0


@pytest.mark.asyncio
async def test_consume_handoff(store):
    await store.register_session("s1", "A", "online", "web")
    await store.register_session("s2", "B", "online", "web")
    await store.create_handoff("HOFF-s1", "s1", {"test": True})

    result = await store.consume_handoff("HOFF-s1", "s2")
    assert result["consumed_by"] == "s2"
    assert result["consumed_at"] is not None


# ── Snapshot ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_snapshot(store):
    await store.register_session("s1", "A", "online", "web", company="BOSS")
    await store.register_session("s2", "B", "local", "opencode", company="CSG")
    await store.create_claim("c1", "s1", "exclusive")
    await store.create_request("REQ-001", "s1", "Need something")

    snap = await store.snapshot()
    assert snap["active_sessions"] == 2
    assert snap["active_claims"] == 1
    assert snap["open_requests"] == 1
    assert snap["pending_handoffs"] == 0
