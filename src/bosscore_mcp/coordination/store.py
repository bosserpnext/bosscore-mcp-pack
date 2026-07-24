"""Persistent coordination registry — SQLite + WAL for PACTE-BOSS multi-agent coordination.

Sessions, claims, events, requests, handoffs — all survive restarts.
Uses sqlite3 (stdlib, no external deps) with WAL mode for concurrent reads.
All writes go through asyncio.to_thread() for non-blocking I/O.

Security: no secrets, tokens, or credentials in this store. Everything is operational state.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import threading

DEFAULT_STORE_DIR = Path(os.getenv("BOSSCORE_MCP_STORE_DIR", Path.home() / ".bosscore-mcp"))
DEFAULT_DB_PATH = DEFAULT_STORE_DIR / "coordination.db"

SCHEMA_V1 = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    agent_name   TEXT NOT NULL,
    agent_type   TEXT NOT NULL CHECK(agent_type IN ('local', 'online')),
    runtime      TEXT NOT NULL,
    task_id      TEXT,
    task_title   TEXT,
    company      TEXT,
    started_at   REAL NOT NULL,
    last_heartbeat_at REAL NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'blocked', 'handoff_pending', 'closed', 'expired', 'abandoned')),
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id      TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    mode          TEXT NOT NULL CHECK(mode IN ('observe', 'shared', 'exclusive', 'integrate', 'deploy')),
    task_id       TEXT,
    task_title    TEXT,
    company       TEXT,
    repositories_json TEXT DEFAULT '[]',
    resources_json    TEXT DEFAULT '[]',
    base_shas_json    TEXT DEFAULT '{}',
    target_shas_json  TEXT DEFAULT '{}',
    branch        TEXT,
    worktree      TEXT,
    started_at    REAL NOT NULL,
    expires_at    REAL NOT NULL,
    last_heartbeat_at REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'blocked', 'handoff_pending', 'released', 'expired', 'abandoned', 'integrated')),
    notes         TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_claims_session ON claims(session_id);
CREATE INDEX IF NOT EXISTS idx_claims_status  ON claims(status);
CREATE INDEX IF NOT EXISTS idx_claims_expires ON claims(expires_at);
CREATE INDEX IF NOT EXISTS idx_claims_mode    ON claims(mode);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    at          REAL NOT NULL,
    type        TEXT NOT NULL,
    repo        TEXT,
    path        TEXT,
    sha         TEXT,
    command     TEXT,
    summary     TEXT,
    data_json   TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_at      ON events(session_id, at);

CREATE TABLE IF NOT EXISTS requests (
    request_id     TEXT PRIMARY KEY,
    from_session   TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    target_session TEXT REFERENCES sessions(session_id),
    target_scope   TEXT,
    need           TEXT NOT NULL,
    acceptance_json TEXT DEFAULT '[]',
    priority       TEXT NOT NULL DEFAULT 'medium'
        CHECK(priority IN ('low', 'medium', 'high', 'critical')),
    status         TEXT NOT NULL DEFAULT 'open'
        CHECK(status IN ('open', 'accepted', 'in_progress', 'completed', 'rejected', 'cancelled')),
    resolution     TEXT,
    related_handoff_id TEXT,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_requests_from   ON requests(from_session);
CREATE INDEX IF NOT EXISTS idx_requests_target ON requests(target_session);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);

CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id     TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    content_json   TEXT NOT NULL,
    created_at     REAL NOT NULL,
    consumed_by    TEXT,
    consumed_at    REAL
);

CREATE INDEX IF NOT EXISTS idx_handoffs_session  ON handoffs(session_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_consumed ON handoffs(consumed_by);
"""


class CoordinationStore:
    """Thread-safe, atomic coordination registry backed by SQLite+WAL.

    All public methods are async and run DB operations via asyncio.to_thread().
    The connection is per-thread; we use a dedicated thread with its own connection.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._initialized = False

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create the thread-local connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(SCHEMA_V1)
        conn.commit()
        self._initialized = True

    async def _ensure_init(self) -> None:
        if not self._initialized:
            await asyncio.to_thread(self._init_schema)

    # ── Sessions ───────────────────────────────────────────────────────────────

    async def register_session(
        self, session_id: str, agent_name: str, agent_type: str, runtime: str,
        *, task_id: str = "", task_title: str = "", company: str = "",
    ) -> dict[str, Any]:
        await self._ensure_init()
        now = time.time()
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                c.execute(
                    """INSERT OR REPLACE INTO sessions
                       (session_id, agent_name, agent_type, runtime, task_id, task_title, company,
                        started_at, last_heartbeat_at, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                    (session_id, agent_name, agent_type, runtime, task_id, task_title, company, now, now),
                )
                c.commit()
                return self._session_row(c, session_id)
        return await asyncio.to_thread(_do)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        await self._ensure_init()
        def _do() -> dict | None:
            c = self._get_conn()
            return self._session_row(c, session_id)
        return await asyncio.to_thread(_do)

    async def list_sessions(
        self, *, status: str | None = None, company: str | None = None,
    ) -> list[dict[str, Any]]:
        await self._ensure_init()
        def _do() -> list:
            c = self._get_conn()
            q = "SELECT * FROM sessions WHERE 1=1"
            params: list = []
            if status:
                q += " AND status = ?"
                params.append(status)
            if company:
                q += " AND company = ?"
                params.append(company)
            q += " ORDER BY last_heartbeat_at DESC"
            rows = c.execute(q, params).fetchall()
            return [_row_dict(r) for r in rows]
        return await asyncio.to_thread(_do)

    async def heartbeat(self, session_id: str, *, status: str | None = None) -> dict[str, Any]:
        await self._ensure_init()
        now = time.time()
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                if status:
                    c.execute(
                        "UPDATE sessions SET last_heartbeat_at=?, status=? WHERE session_id=?",
                        (now, status, session_id),
                    )
                else:
                    c.execute(
                        "UPDATE sessions SET last_heartbeat_at=? WHERE session_id=?",
                        (now, session_id),
                    )
                # Also update claim heartbeat
                c.execute(
                    "UPDATE claims SET last_heartbeat_at=? WHERE session_id=? AND status='active'",
                    (now, session_id),
                )
                c.commit()
                return self._session_row(c, session_id)
        return await asyncio.to_thread(_do)

    async def close_session(self, session_id: str) -> dict[str, Any]:
        await self._ensure_init()
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                c.execute("UPDATE sessions SET status='closed' WHERE session_id=?", (session_id,))
                c.execute("UPDATE claims SET status='released' WHERE session_id=? AND status='active'", (session_id,))
                c.commit()
                return self._session_row(c, session_id)
        return await asyncio.to_thread(_do)

    async def expire_sessions(self) -> int:
        """Mark sessions as expired if they haven't heartbeat'd. Returns count."""
        await self._ensure_init()
        now = time.time()
        def _do() -> int:
            with self._lock:
                c = self._get_conn()
                # Expire claims first
                c.execute(
                    "UPDATE claims SET status='expired' WHERE status='active' AND expires_at < ?",
                    (now,),
                )
                claim_count = c.rowcount
                # Then expire sessions with no active claims
                c.execute(
                    """UPDATE sessions SET status='expired'
                       WHERE status='active' AND last_heartbeat_at < ?
                       AND session_id NOT IN (SELECT session_id FROM claims WHERE status='active')""",
                    (now - 3600,),  # 1h grace period
                )
                session_count = c.rowcount
                c.commit()
                return claim_count + session_count
        return await asyncio.to_thread(_do)

    # ── Claims ─────────────────────────────────────────────────────────────────

    async def create_claim(
        self, claim_id: str, session_id: str, mode: str, *,
        task_id: str = "", task_title: str = "", company: str = "",
        repositories: list[str] | None = None,
        resources: list[str] | None = None,
        base_shas: dict[str, str] | None = None,
        branch: str = "", worktree: str = "",
        ttl: int = 3600, notes: str = "",
    ) -> dict[str, Any]:
        await self._ensure_init()
        now = time.time()
        repos_json = json.dumps(repositories or [])
        res_json = json.dumps(resources or [])
        shas_json = json.dumps(base_shas or {})
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                c.execute(
                    """INSERT INTO claims
                       (claim_id, session_id, mode, task_id, task_title, company,
                        repositories_json, resources_json, base_shas_json,
                        branch, worktree, started_at, expires_at, last_heartbeat_at,
                        status, notes)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?)""",
                    (claim_id, session_id, mode, task_id, task_title, company,
                     repos_json, res_json, shas_json,
                     branch, worktree, now, now + ttl, now, notes),
                )
                c.commit()
                return self._claim_row(c, claim_id)
        return await asyncio.to_thread(_do)

    async def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        await self._ensure_init()
        def _do() -> dict | None:
            c = self._get_conn()
            return self._claim_row(c, claim_id)
        return await asyncio.to_thread(_do)

    async def list_claims(
        self, *, session_id: str | None = None, status: str | None = None,
        mode: str | None = None, company: str | None = None,
    ) -> list[dict[str, Any]]:
        await self._ensure_init()
        def _do() -> list:
            c = self._get_conn()
            q = "SELECT * FROM claims WHERE 1=1"
            params: list = []
            if session_id:
                q += " AND session_id = ?"
                params.append(session_id)
            if status:
                q += " AND status = ?"
                params.append(status)
            if mode:
                q += " AND mode = ?"
                params.append(mode)
            if company:
                q += " AND company = ?"
                params.append(company)
            q += " ORDER BY started_at DESC"
            return [_row_dict(r) for r in c.execute(q, params).fetchall()]
        return await asyncio.to_thread(_do)

    async def extend_claim(self, claim_id: str, ttl: int) -> dict[str, Any]:
        await self._ensure_init()
        now = time.time()
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                c.execute(
                    "UPDATE claims SET expires_at=?, last_heartbeat_at=? WHERE claim_id=?",
                    (now + ttl, now, claim_id),
                )
                c.commit()
                return self._claim_row(c, claim_id)
        return await asyncio.to_thread(_do)

    async def release_claim(self, claim_id: str) -> dict[str, Any]:
        await self._ensure_init()
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                c.execute("UPDATE claims SET status='released' WHERE claim_id=?", (claim_id,))
                c.commit()
                return self._claim_row(c, claim_id)
        return await asyncio.to_thread(_do)

    async def check_conflicts(
        self, resources: list[str], *, exclude_claim_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find active claims that overlap with the given resources."""
        await self._ensure_init()
        import json as _json
        def _do() -> list:
            c = self._get_conn()
            q = "SELECT * FROM claims WHERE status='active'"
            params: list = []
            if exclude_claim_id:
                q += " AND claim_id != ?"
                params.append(exclude_claim_id)
            rows = c.execute(q, params).fetchall()
            conflicts = []
            for r in rows:
                claim_resources = _json.loads(r["resources_json"] or "[]")
                overlap = set(claim_resources) & set(resources)
                if overlap:
                    d = _row_dict(r)
                    d["conflicting_resources"] = list(overlap)
                    conflicts.append(d)
            return conflicts
        return await asyncio.to_thread(_do)

    # ── Events ──────────────────────────────────────────────────────────────────

    async def append_event(
        self, session_id: str, event_type: str, *,
        repo: str = "", path: str = "", sha: str = "",
        command: str = "", summary: str = "", data: dict | None = None,
    ) -> dict[str, Any]:
        await self._ensure_init()
        now = time.time()
        data_json = json.dumps(data or {})
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                cur = c.execute(
                    """INSERT INTO events (session_id, at, type, repo, path, sha, command, summary, data_json)
                       VALUES (?,?,?,?,?,?,?,?,?)
                       RETURNING id""",
                    (session_id, now, event_type, repo, path, sha, command, summary, data_json),
                )
                row = cur.fetchone()
                last_id = row[0]
                c.commit()
                row = c.execute("SELECT * FROM events WHERE id = ?", (last_id,)).fetchone()
                return _row_dict(row)
        return await asyncio.to_thread(_do)

    async def list_events(
        self, session_id: str, *, limit: int = 100, before_id: int | None = None,
    ) -> list[dict[str, Any]]:
        await self._ensure_init()
        def _do() -> list:
            c = self._get_conn()
            if before_id:
                rows = c.execute(
                    "SELECT * FROM events WHERE session_id=? AND id < ? ORDER BY id DESC LIMIT ?",
                    (session_id, before_id, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM events WHERE session_id=? ORDER BY id DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            return [_row_dict(r) for r in reversed(rows)]
        return await asyncio.to_thread(_do)

    async def export_journal(self, session_id: str) -> str:
        """Generate Markdown journal from event stream."""
        await self._ensure_init()
        def _do() -> str:
            c = self._get_conn()
            session = self._session_row(c, session_id)
            if not session:
                return f"# Journal — {session_id}\n\nSession non trouvée.\n"
            events = c.execute(
                "SELECT * FROM events WHERE session_id=? ORDER BY at ASC",
                (session_id,),
            ).fetchall()

            lines = [
                f"# Journal — {session_id}",
                "",
                "## Identité",
                f"- Agent : {session['agent_name']}",
                f"- Type : {session['agent_type']}",
                f"- Runtime : {session['runtime']}",
                f"- Tâche : {session.get('task_id', '')} — {session.get('task_title', '')}",
                f"- Compagnie : {session.get('company', '')}",
                f"- Statut : {session['status']}",
                "",
                "## Événements",
                "",
            ]
            for evt in events:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(evt["at"]))
                lines.append(f"### {ts} — {evt['type']}")
                if evt["repo"]:
                    lines.append(f"- Repo : `{evt['repo']}`")
                if evt["path"]:
                    lines.append(f"- Fichier : `{evt['path']}`")
                if evt["sha"]:
                    lines.append(f"- SHA : `{evt['sha']}`")
                if evt["command"]:
                    lines.append(f"- Commande : `{evt['command']}`")
                if evt["summary"]:
                    lines.append(f"- Résumé : {evt['summary']}")
                data = json.loads(evt["data_json"] or "{}")
                if data:
                    lines.append(f"- Données : `{json.dumps(data)}`")
                lines.append("")
            return "\n".join(lines)
        return await asyncio.to_thread(_do)

    # ── Requests ────────────────────────────────────────────────────────────────

    async def create_request(
        self, request_id: str, from_session: str, need: str, *,
        target_session: str | None = None, target_scope: str = "",
        acceptance: list[str] | None = None, priority: str = "medium",
    ) -> dict[str, Any]:
        await self._ensure_init()
        now = time.time()
        acc_json = json.dumps(acceptance or [])
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                c.execute(
                    """INSERT INTO requests
                       (request_id, from_session, target_session, target_scope, need,
                        acceptance_json, priority, status, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,'open',?,?)""",
                    (request_id, from_session, target_session or None, target_scope, need,
                     acc_json, priority, now, now),
                )
                c.commit()
                row = c.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
                return _row_dict(row)
        return await asyncio.to_thread(_do)

    async def list_requests(
        self, *, from_session: str | None = None, target_session: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        await self._ensure_init()
        def _do() -> list:
            c = self._get_conn()
            q = "SELECT * FROM requests WHERE 1=1"
            params: list = []
            if from_session:
                q += " AND from_session = ?"
                params.append(from_session)
            if target_session:
                q += " AND target_session = ?"
                params.append(target_session)
            if status:
                q += " AND status = ?"
                params.append(status)
            q += " ORDER BY created_at DESC"
            return [_row_dict(r) for r in c.execute(q, params).fetchall()]
        return await asyncio.to_thread(_do)

    async def accept_request(
        self, request_id: str, target_session: str,
    ) -> dict[str, Any]:
        await self._ensure_init()
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                c.execute(
                    """UPDATE requests SET target_session=?, status='accepted', updated_at=? WHERE request_id=?""",
                    (target_session, time.time(), request_id),
                )
                c.commit()
                row = c.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
                return _row_dict(row)
        return await asyncio.to_thread(_do)

    async def close_request(
        self, request_id: str, status: str, *, resolution: str = "",
    ) -> dict[str, Any]:
        """Close a request with final status (completed/rejected/cancelled)."""
        await self._ensure_init()
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                c.execute(
                    "UPDATE requests SET status=?, resolution=?, updated_at=? WHERE request_id=?",
                    (status, resolution, time.time(), request_id),
                )
                c.commit()
                row = c.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
                return _row_dict(row)
        return await asyncio.to_thread(_do)

    # ── Handoffs ────────────────────────────────────────────────────────────────

    async def create_handoff(
        self, handoff_id: str, session_id: str, content: dict[str, Any],
    ) -> dict[str, Any]:
        await self._ensure_init()
        now = time.time()
        content_json = json.dumps(content)
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                c.execute(
                    "INSERT INTO handoffs (handoff_id, session_id, content_json, created_at) VALUES (?,?,?,?)",
                    (handoff_id, session_id, content_json, now),
                )
                # Mark session as handoff_pending
                c.execute("UPDATE sessions SET status='handoff_pending' WHERE session_id=?", (session_id,))
                c.commit()
                row = c.execute("SELECT * FROM handoffs WHERE handoff_id=?", (handoff_id,)).fetchone()
                return _row_dict(row)
        return await asyncio.to_thread(_do)

    async def get_handoff(self, handoff_id: str) -> dict[str, Any] | None:
        await self._ensure_init()
        def _do() -> dict | None:
            c = self._get_conn()
            row = c.execute("SELECT * FROM handoffs WHERE handoff_id=?", (handoff_id,)).fetchone()
            return _row_dict(row) if row else None
        return await asyncio.to_thread(_do)

    async def list_handoffs(
        self, *, session_id: str | None = None, consumed: bool | None = None,
    ) -> list[dict[str, Any]]:
        await self._ensure_init()
        def _do() -> list:
            c = self._get_conn()
            q = "SELECT * FROM handoffs WHERE 1=1"
            params: list = []
            if session_id:
                q += " AND session_id = ?"
                params.append(session_id)
            if consumed is True:
                q += " AND consumed_by IS NOT NULL"
            elif consumed is False:
                q += " AND consumed_by IS NULL"
            q += " ORDER BY created_at DESC"
            return [_row_dict(r) for r in c.execute(q, params).fetchall()]
        return await asyncio.to_thread(_do)

    async def consume_handoff(self, handoff_id: str, consumer_session_id: str) -> dict[str, Any]:
        await self._ensure_init()
        def _do() -> dict:
            with self._lock:
                c = self._get_conn()
                c.execute(
                    "UPDATE handoffs SET consumed_by=?, consumed_at=? WHERE handoff_id=?",
                    (consumer_session_id, time.time(), handoff_id),
                )
                c.commit()
                row = c.execute("SELECT * FROM handoffs WHERE handoff_id=?", (handoff_id,)).fetchone()
                return _row_dict(row)
        return await asyncio.to_thread(_do)

    # ── Enforcement (Levels 3-4) ─────────────────────────────────────────────────

    async def enforce_claim(
        self, session_id: str, resources: list[str], *, mode: str = "block",
    ) -> dict[str, Any]:
        """Check that session has an active claim covering ALL resources.
        
        mode='block': returns error dict if no valid claim (Level 4)
        mode='warn': returns warning but doesn't block (Level 3)
        """
        await self._ensure_init()
        def _do() -> dict:
            c = self._get_conn()
            # Find active claims for this session
            claims = c.execute(
                "SELECT * FROM claims WHERE session_id=? AND status='active'",
                (session_id,),
            ).fetchall()
            
            if not claims:
                msg = f"No active claim for session {session_id}. Create one via boss_work_claim."
                return {"ok": False, "blocked": mode == "block", "reason": msg, "missing": resources}
            
            # Check each resource against all active claims
            claimed: set[str] = set()
            for claim in claims:
                claim_resources = json.loads(claim["resources_json"] or "[]")
                claimed.update(claim_resources)
            
            missing = [r for r in resources if r not in claimed]
            if not missing:
                return {"ok": True, "blocked": False, "claim_ids": [cl["claim_id"] for cl in claims]}
            
            # Check if ANY other session claims these (conflict warning Level 3)
            conflicts = c.execute(
                "SELECT * FROM claims WHERE status='active' AND session_id != ?",
                (session_id,),
            ).fetchall()
            external_conflicts = []
            for cl in conflicts:
                cl_res = set(json.loads(cl["resources_json"] or "[]"))
                overlap = cl_res & set(missing)
                if overlap:
                    external_conflicts.append({
                        "claim_id": cl["claim_id"],
                        "session_id": cl["session_id"],
                        "agent_mode": cl["mode"],
                        "conflicting": list(overlap),
                    })
            
            msg = f"Session {session_id} has no claim on: {missing}"
            warnings = []
            if external_conflicts:
                msg += f". External claims detected: {len(external_conflicts)}"
                warnings = external_conflicts
            
            return {
                "ok": False,
                "blocked": mode == "block",
                "reason": msg,
                "missing": missing,
                "warnings": warnings,
                "hint": "Create a claim via boss_work_claim before writing.",
            }
        return await asyncio.to_thread(_do)

    # ── Snapshot ───────────────────────────────────────────────────────────────

    async def snapshot(self) -> dict[str, Any]:
        """Full coordination snapshot — sessions, claims, requests, handoffs."""
        await self._ensure_init()
        def _do() -> dict:
            c = self._get_conn()
            sessions = [_row_dict(r) for r in c.execute(
                "SELECT * FROM sessions WHERE status IN ('active','blocked','handoff_pending') ORDER BY last_heartbeat_at DESC"
            ).fetchall()]
            claims = [_row_dict(r) for r in c.execute(
                "SELECT * FROM claims WHERE status='active' ORDER BY started_at DESC"
            ).fetchall()]
            requests_open = [_row_dict(r) for r in c.execute(
                "SELECT * FROM requests WHERE status='open' ORDER BY created_at DESC"
            ).fetchall()]
            handoffs_pending = [_row_dict(r) for r in c.execute(
                "SELECT * FROM handoffs WHERE consumed_by IS NULL ORDER BY created_at DESC LIMIT 20"
            ).fetchall()]
            return {
                "at": time.time(),
                "active_sessions": len(sessions),
                "active_claims": len(claims),
                "open_requests": len(requests_open),
                "pending_handoffs": len(handoffs_pending),
                "sessions": sessions,
                "claims": claims,
                "requests": requests_open,
                "handoffs": handoffs_pending,
            }
        return await asyncio.to_thread(_do)

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _session_row(self, c: sqlite3.Connection, session_id: str) -> dict | None:
        row = c.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        return _row_dict(row) if row else None

    def _claim_row(self, c: sqlite3.Connection, claim_id: str) -> dict | None:
        row = c.execute("SELECT * FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
        return _row_dict(row) if row else None

    # Used by tests
    @property
    def db_path(self) -> Path:
        return self._db_path


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


# Singleton (lazy init)
_store: CoordinationStore | None = None


def get_coordination_store() -> CoordinationStore:
    global _store
    if _store is None:
        _store = CoordinationStore()
    return _store
