"""CoordinationProvider — PACTE-BOSS multi-agent coordination tools for the MCP registry.

28 tools: sessions (5), claims (7), events (3), requests (4), handoffs (3),
workspaces (3), integration (3). All follow the ToolSpec pattern with
outputSchema, scope enforcement, and redacted logging.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from typing import Any

from typing import TYPE_CHECKING

from ..core.registry import ToolSpec, object_schema
from .store import CoordinationStore, get_coordination_store

if TYPE_CHECKING:
    from ..documents.policy import PathPolicy
    from ..exec import ExecProvider

_OUTPUT_OK: dict = {"type": "object"}  # generic — structuredContent = raw handler output


class CoordinationProvider:
    """Produces ToolSpec instances for PACTE-BOSS coordination.

    Accepts optional references to PathPolicy and ExecProvider so that
    worktree paths created via workspace_create are automatically registered
    for file access and command execution.
    """

    def __init__(
        self,
        store: CoordinationStore | None = None,
        *,
        policy: PathPolicy | None = None,
        exec_provider: ExecProvider | None = None,
    ) -> None:
        self._store = store or get_coordination_store()
        self._policy = policy
        self._exec_provider = exec_provider

    def _deregister_worktree(self, session_id: str) -> None:
        """Remove worktree path from policy and exec provider (best-effort)."""
        worktree_path = f"/home/bomoja/worktrees/{session_id}"
        if self._policy is not None:
            try:
                self._policy.remove_root(worktree_path, session_id=session_id)
            except Exception:
                pass
        if self._exec_provider is not None:
            try:
                self._exec_provider.remove_allowed_path(worktree_path)
            except Exception:
                pass

    def specs(self) -> list[ToolSpec]:
        return [
            # ── Sessions ──────────────────────────────────────────────────
            self._boss_agent_register(),
            self._boss_agent_session_get(),
            self._boss_agent_session_list(),
            self._boss_agent_heartbeat(),
            self._boss_agent_session_close(),
            # ── Claims ────────────────────────────────────────────────────
            self._boss_coordination_snapshot(),
            self._boss_work_claim(),
            self._boss_work_claim_get(),
            self._boss_work_claim_list(),
            self._boss_work_claim_extend(),
            self._boss_work_claim_release(),
            self._boss_conflict_check(),
            self._boss_claim_enforce(),  # Level 3-4
            # ── Events ─────────────────────────────────────────────────────
            self._boss_work_event_append(),
            self._boss_work_events_list(),
            self._boss_work_journal_export(),
            # ── Requests ───────────────────────────────────────────────────
            self._boss_work_request_create(),
            self._boss_work_request_list(),
            self._boss_work_request_accept(),
            self._boss_work_request_close(),
            # ── Handoffs ───────────────────────────────────────────────────
            self._boss_work_handoff_create(),
            self._boss_work_handoff_get(),
            self._boss_work_handoff_list(),
            # ── Workspaces ─────────────────────────────────────────────────
            self._boss_workspace_create(),
            self._boss_workspace_status(),
            self._boss_workspace_cleanup_plan(),
            self._boss_workspace_cleanup_execute(),
            # ── Integration ────────────────────────────────────────────────
            self._boss_integration_plan(),
            self._boss_integration_execute(),
            self._boss_integration_verify(),
        ]

    # ═══════════════════════════════════════════════════════════════════════════
    # Sessions
    # ═══════════════════════════════════════════════════════════════════════════

    def _boss_agent_register(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            session_id = args.get("session_id") or _new_session_id(args)
            agent_type = args.get("agent_type", "online")
            if agent_type not in ("local", "online"):
                agent_type = "online"
            result = await self._store.register_session(
                session_id=session_id,
                agent_name=args.get("agent_name", "unknown"),
                agent_type=agent_type,
                runtime=args.get("runtime", "unknown"),
                task_id=args.get("task_id", ""),
                task_title=args.get("task_title", ""),
                company=args.get("company", ""),
            )
            await self._store.append_event(session_id, "session.started")
            return result

        return ToolSpec(
            name="boss_agent_register",
            description="Enregistrer une nouvelle session agent dans le registre PACTE-BOSS. À appeler en tout premier.",
            input_schema=object_schema(
                properties={
                    "session_id":  {"type": "string", "description": "ID session. Généré si absent. Format: AAAAMMJJ-env-agent-tache"},
                    "agent_name":  {"type": "string", "description": "Nom de l'agent (ChatGPT, Claude, OpenCode...)"},
                    "agent_type":  {"type": "string", "enum": ["local", "online"], "description": "local (machine opérateur) ou online (SaaS/cloud)"},
                    "runtime":     {"type": "string", "description": "Environnement (chatgpt.com, claude.ai, opencode...)"},
                    "task_id":     {"type": "string", "description": "Identifiant métier de la tâche"},
                    "task_title":  {"type": "string", "description": "Titre descriptif"},
                    "company":     {"type": "string", "description": "Compagnie (BOSS, CSG, ACW...)"},
                },
                required=["agent_name", "agent_type", "runtime"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=False,
        )

    def _boss_agent_session_get(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            session = await self._store.get_session(args["session_id"])
            return {"ok": session is not None, "data": session or {}}

        return ToolSpec(
            name="boss_agent_session_get",
            description="Obtenir les détails d'une session agent (nom, type, runtime, statut, dernier heartbeat).",
            input_schema=object_schema(
                properties={"session_id": {"type": "string", "description": "ID de la session"}},
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_agent_session_list(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            sessions = await self._store.list_sessions(
                status=args.get("status"),
                company=args.get("company"),
            )
            return {"ok": True, "data": {"sessions": sessions, "count": len(sessions)}}

        return ToolSpec(
            name="boss_agent_session_list",
            description="Lister les sessions agents. Filtrable par statut et compagnie.",
            input_schema=object_schema(properties={
                "status":  {"type": "string", "enum": ["active", "blocked", "handoff_pending", "closed", "expired", "abandoned"]},
                "company": {"type": "string", "description": "Compagnie (BOSS, CSG...)"},
            }),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_agent_heartbeat(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            session = await self._store.heartbeat(
                args["session_id"],
                status=args.get("status"),
            )
            await self._store.append_event(args["session_id"], "session.heartbeat")
            return {"ok": True, "data": session}

        return ToolSpec(
            name="boss_agent_heartbeat",
            description="Envoyer un heartbeat pour maintenir la session active. À appeler périodiquement (toutes les ~5 min).",
            input_schema=object_schema(
                properties={
                    "session_id": {"type": "string", "description": "ID de la session"},
                    "status":     {"type": "string", "enum": ["active", "blocked", "handoff_pending"], "description": "Nouveau statut si changement"},
                },
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=True,
        )

    def _boss_agent_session_close(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            session = await self._store.close_session(args["session_id"])
            await self._store.append_event(args["session_id"], "session.closed")
            self._deregister_worktree(args["session_id"])
            return {"ok": True, "data": session}

        return ToolSpec(
            name="boss_agent_session_close",
            description="Fermer une session et libérer tous ses claims actifs.",
            input_schema=object_schema(
                properties={"session_id": {"type": "string"}},
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=True, idempotent=False,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Claims
    # ═══════════════════════════════════════════════════════════════════════════

    def _boss_coordination_snapshot(self) -> ToolSpec:
        async def handler(args: dict) -> dict:  # noqa: ARG001
            snap = await self._store.snapshot()
            return {"ok": True, "data": snap}

        return ToolSpec(
            name="boss_coordination_snapshot",
            description="Obtenir l'état complet de la coordination : sessions actives, claims en cours, demandes ouvertes, handoffs en attente. À consulter AVANT toute action.",
            input_schema=object_schema(),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_work_claim(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            # Check conflicts first
            resources = args.get("resources", [])
            if resources:
                conflicts = await self._store.check_conflicts(resources)
                if conflicts:
                    return {
                        "ok": False,
                        "data": {"error": "conflict", "conflicts": conflicts},
                    }
            claim_id = args.get("claim_id") or _new_claim_id(args.get("session_id", "unknown"))
            claim = await self._store.create_claim(
                claim_id=claim_id,
                session_id=args["session_id"],
                mode=args.get("mode", "exclusive"),
                task_id=args.get("task_id", ""),
                task_title=args.get("task_title", ""),
                company=args.get("company", ""),
                repositories=args.get("repositories", []),
                resources=resources,
                base_shas=args.get("base_shas", {}),
                branch=args.get("branch", ""),
                worktree=args.get("worktree", ""),
                ttl=args.get("ttl", 3600),
                notes=args.get("notes", ""),
            )
            await self._store.append_event(args["session_id"], "claim.created", data={"claim_id": claim_id})
            return {"ok": True, "data": claim}

        return ToolSpec(
            name="boss_work_claim",
            description="Créer un claim (déclaration de périmètre) avant de modifier du code, Git ou WordPress. Vérifie automatiquement les conflits.",
            input_schema=object_schema(
                properties={
                    "session_id":   {"type": "string", "description": "ID de la session"},
                    "claim_id":     {"type": "string", "description": "ID du claim. Généré si absent."},
                    "mode":         {"type": "string", "enum": ["observe", "shared", "exclusive", "integrate", "deploy"], "description": "Mode (défaut: exclusive)"},
                    "task_id":      {"type": "string"},
                    "task_title":   {"type": "string"},
                    "company":      {"type": "string"},
                    "repositories": {"type": "array", "items": {"type": "string"}},
                    "resources":    {"type": "array", "items": {"type": "string"}, "description": "Ressources réservées (format: type:scope:id)"},
                    "base_shas":    {"type": "object", "additionalProperties": {"type": "string"}, "description": "SHA de départ par repo"},
                    "branch":       {"type": "string"},
                    "worktree":     {"type": "string"},
                    "ttl":          {"type": "integer", "description": "Durée de vie en secondes (défaut: 3600 = 1h)"},
                    "notes":        {"type": "string"},
                },
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=False,
        )

    def _boss_work_claim_get(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            claim = await self._store.get_claim(args["claim_id"])
            return {"ok": claim is not None, "data": claim or {}}

        return ToolSpec(
            name="boss_work_claim_get",
            description="Lire un claim spécifique.",
            input_schema=object_schema(
                properties={"claim_id": {"type": "string"}},
                required=["claim_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_work_claim_list(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            claims = await self._store.list_claims(
                session_id=args.get("session_id"),
                status=args.get("status"),
                mode=args.get("mode"),
                company=args.get("company"),
            )
            return {"ok": True, "data": {"claims": claims, "count": len(claims)}}

        return ToolSpec(
            name="boss_work_claim_list",
            description="Lister les claims. Filtrable par session, statut, mode, compagnie.",
            input_schema=object_schema(properties={
                "session_id": {"type": "string"},
                "status":     {"type": "string", "enum": ["active", "blocked", "handoff_pending", "released", "expired", "abandoned", "integrated"]},
                "mode":       {"type": "string", "enum": ["observe", "shared", "exclusive", "integrate", "deploy"]},
                "company":    {"type": "string"},
            }),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_work_claim_extend(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            claim = await self._store.extend_claim(args["claim_id"], args.get("ttl", 1800))
            return {"ok": True, "data": claim}

        return ToolSpec(
            name="boss_work_claim_extend",
            description="Prolonger la durée de vie d'un claim.",
            input_schema=object_schema(
                properties={
                    "claim_id": {"type": "string"},
                    "ttl":      {"type": "integer", "description": "Nouvelle durée en secondes (défaut: 1800 = 30min)"},
                },
                required=["claim_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=True,
        )

    def _boss_work_claim_release(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            claim = await self._store.release_claim(args["claim_id"])
            sid = claim.get("session_id", "")
            await self._store.append_event(sid, "claim.released", data={"claim_id": args["claim_id"]})
            if sid:
                self._deregister_worktree(sid)
            return {"ok": True, "data": claim}

        return ToolSpec(
            name="boss_work_claim_release",
            description="Libérer un claim — les ressources redeviennent disponibles.",
            input_schema=object_schema(
                properties={"claim_id": {"type": "string"}},
                required=["claim_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=False,
        )

    def _boss_conflict_check(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            resources = args.get("resources", [])
            conflicts = await self._store.check_conflicts(
                resources,
                exclude_claim_id=args.get("exclude_claim_id"),
            )
            return {"ok": len(conflicts) == 0, "data": {"resources": resources, "conflicts": conflicts, "has_conflicts": len(conflicts) > 0}}

        return ToolSpec(
            name="boss_conflict_check",
            description="Vérifier si des ressources sont déjà réclamées par un autre claim actif. À appeler avant boss_work_claim.",
            input_schema=object_schema(
                properties={
                    "resources":         {"type": "array", "items": {"type": "string"}, "description": "Ressources à vérifier"},
                    "exclude_claim_id":  {"type": "string", "description": "Exclure ce claim de la vérification"},
                },
                required=["resources"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_claim_enforce(self) -> ToolSpec:
        """Level 3-4: enforce active claim before write operations."""
        async def handler(args: dict) -> dict:
            result = await self._store.enforce_claim(
                args["session_id"],
                args.get("resources", []),
                mode=args.get("mode", "block"),
            )
            return result

        return ToolSpec(
            name="boss_claim_enforce",
            description="Vérifier qu'une session a un claim actif sur les ressources spécifiées. Niveau 3 (warn) : avertit. Niveau 4 (block) : refuse l'opération. À appeler AVANT tout Git write, Exec, Deploy ou WordPress write.",
            input_schema=object_schema(
                properties={
                    "session_id": {"type": "string", "description": "ID de la session"},
                    "resources":  {"type": "array", "items": {"type": "string"}, "description": "Ressources à vérifier"},
                    "mode":       {"type": "string", "enum": ["warn", "block"], "description": "warn = avertissement, block = refus (défaut)"},
                },
                required=["session_id", "resources"],
            ),
            output_schema={"type": "object"},
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=True,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Events
    # ═══════════════════════════════════════════════════════════════════════════

    def _boss_work_event_append(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            event = await self._store.append_event(
                session_id=args["session_id"],
                event_type=args["type"],
                repo=args.get("repo", ""),
                path=args.get("path", ""),
                sha=args.get("sha", ""),
                command=args.get("command", ""),
                summary=args.get("summary", ""),
                data=args.get("data"),
            )
            return {"ok": True, "data": event}

        return ToolSpec(
            name="boss_work_event_append",
            description="Ajouter un événement au journal append-only de la session. Types: session.*, file.*, test.*, commit.*, deploy.*, request.*, handoff.*, integration.*, decision.made, blocker.*, risk.*, next_action.defined.",
            input_schema=object_schema(
                properties={
                    "session_id": {"type": "string"},
                    "type":       {"type": "string", "description": "Type d'événement (session.started, file.modified, test.passed, commit.created, deploy.executed, decision.made, blocker.identified...)"},
                    "repo":       {"type": "string"},
                    "path":       {"type": "string"},
                    "sha":        {"type": "string"},
                    "command":    {"type": "string"},
                    "summary":    {"type": "string", "description": "Résumé (ex: '158 tests, 0 failures')"},
                    "data":       {"type": "object", "description": "Données structurées supplémentaires"},
                },
                required=["session_id", "type"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=False,
        )

    def _boss_work_events_list(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            events = await self._store.list_events(
                args["session_id"],
                limit=args.get("limit", 100),
                before_id=args.get("before_id"),
            )
            return {"ok": True, "data": {"events": events, "count": len(events)}}

        return ToolSpec(
            name="boss_work_events_list",
            description="Lister les événements d'une session. Paginable.",
            input_schema=object_schema(
                properties={
                    "session_id": {"type": "string"},
                    "limit":      {"type": "integer", "description": "Max événements (défaut: 100)"},
                    "before_id":  {"type": "integer", "description": "Événements avant cet ID (pagination)"},
                },
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_work_journal_export(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            journal = await self._store.export_journal(args["session_id"])
            return {"ok": True, "data": {"session_id": args["session_id"], "journal_md": journal}}

        return ToolSpec(
            name="boss_work_journal_export",
            description="Exporter le journal complet d'une session en Markdown.",
            input_schema=object_schema(
                properties={"session_id": {"type": "string"}},
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Requests
    # ═══════════════════════════════════════════════════════════════════════════

    def _boss_work_request_create(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            req_id = args.get("request_id") or f"REQ-{hashlib.sha256(os.urandom(8)).hexdigest()[:8].upper()}"
            ts = args.get("target_session", "") or None
            req = await self._store.create_request(
                request_id=req_id,
                from_session=args["from_session"],
                need=args["need"],
                target_session=ts,
                target_scope=args.get("target_scope", ""),
                acceptance=args.get("acceptance", []),
                priority=args.get("priority", "medium"),
            )
            await self._store.append_event(args["from_session"], "request.created", data={"request_id": req_id})
            return {"ok": True, "data": req}

        return ToolSpec(
            name="boss_work_request_create",
            description="Créer une demande de collaboration. Pour tout besoin hors périmètre.",
            input_schema=object_schema(
                properties={
                    "from_session":   {"type": "string"},
                    "need":           {"type": "string", "description": "Description du besoin"},
                    "request_id":     {"type": "string", "description": "ID. Format REQ-... Généré si absent."},
                    "target_session": {"type": "string", "description": "Session destinataire (optionnel)"},
                    "target_scope":   {"type": "string", "description": "Périmètre cible (ex: module:sales:transaction-events)"},
                    "acceptance":     {"type": "array", "items": {"type": "string"}, "description": "Critères d'acceptation"},
                    "priority":       {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                },
                required=["from_session", "need"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=False,
        )

    def _boss_work_request_list(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            reqs = await self._store.list_requests(
                from_session=args.get("from_session"),
                target_session=args.get("target_session"),
                status=args.get("status"),
            )
            return {"ok": True, "data": {"requests": reqs, "count": len(reqs)}}

        return ToolSpec(
            name="boss_work_request_list",
            description="Lister les demandes de collaboration.",
            input_schema=object_schema(properties={
                "from_session":   {"type": "string"},
                "target_session": {"type": "string"},
                "status":         {"type": "string", "enum": ["open", "accepted", "in_progress", "completed", "rejected", "cancelled"]},
            }),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_work_request_accept(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            req = await self._store.accept_request(args["request_id"], args["target_session"])
            await self._store.append_event(args["target_session"], "request.accepted", data={"request_id": args["request_id"]})
            return {"ok": True, "data": req}

        return ToolSpec(
            name="boss_work_request_accept",
            description="Accepter une demande de collaboration et s'y assigner.",
            input_schema=object_schema(
                properties={
                    "request_id":     {"type": "string"},
                    "target_session": {"type": "string", "description": "Session qui accepte"},
                },
                required=["request_id", "target_session"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=False,
        )

    def _boss_work_request_close(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            req = await self._store.close_request(
                args["request_id"],
                args.get("status", "completed"),
                resolution=args.get("resolution", ""),
            )
            await self._store.append_event(
                req.get("from_session", ""), "request.closed",
                data={"request_id": args["request_id"], "status": args.get("status")},
            )
            return {"ok": True, "data": req}

        return ToolSpec(
            name="boss_work_request_close",
            description="Fermer une demande de collaboration (completed/rejected/cancelled).",
            input_schema=object_schema(
                properties={
                    "request_id": {"type": "string"},
                    "status":     {"type": "string", "enum": ["completed", "rejected", "cancelled"]},
                    "resolution": {"type": "string", "description": "Justification en cas de rejet"},
                },
                required=["request_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=False,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Handoffs
    # ═══════════════════════════════════════════════════════════════════════════

    def _boss_work_handoff_create(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            session_id = args["session_id"]
            handoff_id = args.get("handoff_id") or f"HOFF-{session_id}"
            content = {
                "handoff_id": handoff_id,
                "session_id": session_id,
                "mission": {"initial": args.get("mission_initial", "")},
                "work_completed": args.get("work_completed", []),
                "work_partial": args.get("work_partial", []),
                "work_not_started": args.get("work_not_started", []),
                "resources_touched": args.get("resources_touched", []),
                "commits": args.get("commits", []),
                "decisions": args.get("decisions", []),
                "risks_and_debts": args.get("risks_and_debts", []),
                "blockers": args.get("blockers", []),
                "next_safe_action": args.get("next_safe_action", ""),
                "resources_still_held": args.get("resources_still_held", []),
                "resources_released": args.get("resources_released", []),
                "created_at": time.time(),
                "notes": args.get("notes", ""),
            }
            result = await self._store.create_handoff(handoff_id, session_id, content)
            await self._store.append_event(session_id, "handoff.created", data={"handoff_id": handoff_id})
            return result

        return ToolSpec(
            name="boss_work_handoff_create",
            description="Créer un handoff — transmission structurée avant arrêt ou libération. Obligatoire avant de fermer une session avec du travail en cours.",
            input_schema=object_schema(
                properties={
                    "session_id":          {"type": "string"},
                    "handoff_id":          {"type": "string", "description": "ID. Généré si absent."},
                    "mission_initial":     {"type": "string"},
                    "work_completed":      {"type": "array", "items": {"type": "string"}},
                    "work_partial":        {"type": "array", "items": {"type": "string"}},
                    "work_not_started":    {"type": "array", "items": {"type": "string"}},
                    "resources_touched":   {"type": "array", "items": {"type": "string"}},
                    "commits":             {"type": "array", "items": {"type": "object"}},
                    "decisions":           {"type": "array", "items": {"type": "string"}},
                    "risks_and_debts":     {"type": "array", "items": {"type": "string"}},
                    "blockers":            {"type": "array", "items": {"type": "string"}},
                    "next_safe_action":    {"type": "string"},
                    "resources_still_held":{"type": "array", "items": {"type": "string"}},
                    "resources_released":  {"type": "array", "items": {"type": "string"}},
                    "notes":               {"type": "string"},
                },
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=False, idempotent=False,
        )

    def _boss_work_handoff_get(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            handoff = await self._store.get_handoff(args["handoff_id"])
            return {"ok": handoff is not None, "data": handoff or {}}

        return ToolSpec(
            name="boss_work_handoff_get",
            description="Lire un handoff spécifique.",
            input_schema=object_schema(
                properties={"handoff_id": {"type": "string"}},
                required=["handoff_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_work_handoff_list(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            consumed = None
            if "consumed" in args:
                consumed = args["consumed"]
            handoffs = await self._store.list_handoffs(
                session_id=args.get("session_id"),
                consumed=consumed,
            )
            return {"ok": True, "data": {"handoffs": handoffs, "count": len(handoffs)}}

        return ToolSpec(
            name="boss_work_handoff_list",
            description="Lister les handoffs. Par défaut, tous.",
            input_schema=object_schema(properties={
                "session_id": {"type": "string"},
                "consumed":   {"type": "boolean", "description": "Filtrer par statut de consommation"},
            }),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Workspaces
    # ═══════════════════════════════════════════════════════════════════════════

    def _boss_workspace_create(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            session_id = args["session_id"]
            branch = args.get("branch", f"agent/online-unknown/{session_id[:20]}")
            base_path = args.get("base_path", "/home/bomoja/worktrees")
            worktree_path = f"{base_path}/{session_id}"

            # ── Register worktree path for file access + exec ─────────
            # Best-effort: failure here must not block workspace creation.
            registered = []
            if self._policy is not None:
                try:
                    self._policy.add_root(worktree_path, session_id=session_id)
                    registered.append("documents")
                except Exception:
                    pass
            if self._exec_provider is not None:
                try:
                    self._exec_provider.add_allowed_path(worktree_path)
                    registered.append("exec")
                except Exception:
                    pass

            # Generate the git worktree commands
            commands = [
                f"# Create worktree for session {session_id}",
                f"mkdir -p {base_path}",
                f"cd /home/bomoja/repos/companies",
                f"git worktree add {worktree_path} -b {branch} master",
                f"echo 'Worktree ready: {worktree_path}'",
            ]

            return {
                "ok": True,
                "data": {
                    "session_id": session_id,
                    "branch": branch,
                    "worktree_path": worktree_path,
                    "commands": "\n".join(commands),
                    "registered_for": registered,
                    "note": "Execute these commands via boss_exec on VPS or manually on local machine.",
                },
            }

        return ToolSpec(
            name="boss_workspace_create",
            description="Planifier la création d'un worktree Git isolé pour une session. Retourne les commandes à exécuter.",
            input_schema=object_schema(
                properties={
                    "session_id": {"type": "string"},
                    "branch":     {"type": "string", "description": "Branche. Format: agent/<local|online>-<agent>/<task-slug>"},
                    "base_path":  {"type": "string", "description": "Dossier parent des worktrees. Défaut: /home/bomoja/worktrees"},
                },
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_workspace_status(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            return {
                "ok": True,
                "data": {
                    "session_id": args["session_id"],
                    "commands": [
                        f"# Check worktree status",
                        f"cd /home/bomoja/worktrees/{args['session_id']} 2>/dev/null || echo 'Worktree not found'",
                        "git status --short",
                        "git log --oneline -3",
                        "git branch --show-current",
                    ],
                    "note": "Execute these via boss_exec on VPS to verify worktree state.",
                },
            }

        return ToolSpec(
            name="boss_workspace_status",
            description="Vérifier le statut d'un worktree (branche, SHA, fichiers modifiés).",
            input_schema=object_schema(
                properties={"session_id": {"type": "string"}},
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_workspace_cleanup_plan(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            return {
                "ok": True,
                "data": {
                    "session_id": args["session_id"],
                    "commands": [
                        f"# Cleanup worktree plan for session {args['session_id']}",
                        f"# Step 1: Verify branch is merged/integrated",
                        f"git log --oneline origin/master..agent/.../{args['session_id'][:20]}",
                        f"# Step 2: Remove worktree",
                        f"cd /home/bomoja/repos/companies",
                        f"git worktree remove /home/bomoja/worktrees/{args['session_id']} --force 2>/dev/null",
                        f"# Step 3: Delete branch (after merge)",
                        f"git branch -d agent/.../{args['session_id'][:20]} 2>/dev/null",
                    ],
                    "warning": "Verify integration before cleanup. Worktrees with unmerged work MUST NOT be deleted.",
                },
            }

        return ToolSpec(
            name="boss_workspace_cleanup_plan",
            description="Planifier le nettoyage d'un worktree. Retourne les commandes, PAS d'exécution automatique.",
            input_schema=object_schema(
                properties={"session_id": {"type": "string"}},
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_workspace_cleanup_execute(self) -> ToolSpec:
        """Execute cleanup after manual verification (Level 4: requires claim)."""
        async def handler(args: dict) -> dict:
            sid = args["session_id"]
            # Enforce claim before destructive operation
            enforce = await self._store.enforce_claim(
                sid, [f"repo:companies"], mode="block",
            )
            if not enforce["ok"]:
                return enforce

            return {
                "ok": True,
                "data": {
                    "session_id": sid,
                    "commands": [
                        f"cd /home/bomoja/repos/companies",
                        f"git worktree remove /home/bomoja/worktrees/{sid} --force 2>/dev/null",
                        f"git branch -D agent/.../{sid[:20]} 2>/dev/null",
                        f"echo 'Cleanup complete for {sid}'",
                    ],
                    "warning": "Exécutez ces commandes via boss_exec UNIQUEMENT après avoir vérifié l'intégration.",
                },
            }

        return ToolSpec(
            name="boss_workspace_cleanup_execute",
            description="Générer les commandes de nettoyage d'un worktree (après vérification manuelle). Nécessite un claim actif sur repo:companies.",
            input_schema=object_schema(
                properties={"session_id": {"type": "string"}},
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=True, idempotent=False,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Integration
    # ═══════════════════════════════════════════════════════════════════════════

    def _boss_integration_plan(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            session_id = args["session_id"]
            branch = args.get("branch", "")
            return {
                "ok": True,
                "data": {
                    "session_id": session_id,
                    "branch": branch,
                    "commands": [
                        "# Integration plan",
                        f"cd /home/bomoja/repos/companies",
                        "git fetch origin",
                        f"git checkout master && git pull origin master",
                        f"# Verify branch exists:",
                        f"git log --oneline origin/{branch}..origin/master 2>/dev/null || echo 'Branch not on remote'",
                        f"# Merge (dry-run):",
                        f"git merge --no-commit --no-ff origin/{branch} 2>&1 || echo 'CONFLICT DETECTED'",
                        "git merge --abort 2>/dev/null",
                    ],
                    "steps": [
                        "1. Verify handoffs and base SHAs",
                        "2. Replay QA",
                        "3. Resolve conflicts",
                        "4. Update lockfiles and submodules",
                        "5. Verify parent repo",
                        "6. Push",
                        "7. Release integrated claims",
                    ],
                },
            }

        return ToolSpec(
            name="boss_integration_plan",
            description="Planifier l'intégration d'une branche. Retourne le plan et les commandes.",
            input_schema=object_schema(
                properties={
                    "session_id": {"type": "string"},
                    "branch":     {"type": "string", "description": "Branche à intégrer"},
                },
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )

    def _boss_integration_execute(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            branch = args.get("branch", "")
            return {
                "ok": True,
                "data": {
                    "session_id": args["session_id"],
                    "branch": branch,
                    "commands": [
                        "# Integration execution",
                        f"cd /home/bomoja/repos/companies",
                        "git fetch origin",
                        "git checkout master && git pull origin master",
                        f"git merge --no-ff origin/{branch} -m 'integrate: merge {branch}'",
                        "git submodule update --init --recursive",
                        "git push origin master",
                        f"echo 'Integration complete: {branch} → master'",
                    ],
                    "warning": "Execute ONLY after manual conflict resolution. Do NOT force-push.",
                },
            }

        return ToolSpec(
            name="boss_integration_execute",
            description="Exécuter l'intégration d'une branche dans master. Après résolution manuelle des conflits.",
            input_schema=object_schema(
                properties={
                    "session_id": {"type": "string"},
                    "branch":     {"type": "string"},
                },
                required=["session_id", "branch"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:write",),
            read_only=False, destructive=True, idempotent=False,
        )

    def _boss_integration_verify(self) -> ToolSpec:
        async def handler(args: dict) -> dict:
            return {
                "ok": True,
                "data": {
                    "session_id": args["session_id"],
                    "commands": [
                        "# Integration verification",
                        "cd /home/bomoja/repos/companies",
                        "git log --oneline -5",
                        "git status --short",
                        "git submodule status",
                    ],
                    "checks": [
                        "Working tree clean",
                        "Submodules synced",
                        "All handoffs consumed",
                        "Integration claim released",
                    ],
                },
            }

        return ToolSpec(
            name="boss_integration_verify",
            description="Vérifier qu'une intégration est complète et propre.",
            input_schema=object_schema(
                properties={"session_id": {"type": "string"}},
                required=["session_id"],
            ),
            output_schema=_OUTPUT_OK,
            handler=handler,
            required_scopes=("coordination:read",),
            read_only=True, destructive=False, idempotent=True,
        )


# ── ID generators ─────────────────────────────────────────────────────────────

def _new_session_id(args: dict) -> str:
    ts = time.strftime("%Y%m%d")
    env = "local" if args.get("agent_type") == "local" else "online"
    agent = (args.get("agent_name", "unknown") or "unknown").lower().replace(" ", "-")[:12]
    task = (args.get("task_title", "unknown") or "unknown").lower().replace(" ", "-")[:24]
    return f"{ts}-{env}-{agent}-{task}"


def _new_claim_id(session_id: str) -> str:
    short = hashlib.sha256((session_id + os.urandom(8).hex()).encode()).hexdigest()[:8]
    return f"CLAIM-{short}"
