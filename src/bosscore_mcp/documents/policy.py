"""Filesystem authorization policy for document tools.

Roots are dynamic: static roots from BOSSCORE_FILE_ROOTS + dynamically added
worktree paths registered via add_root() at runtime (PACTE-BOSS worktree isolation).

Session-aware: when session_id is passed, relative paths resolve against the
session's worktree (preferred) or the canonical workspace (fallback).
session_roots map prevents cross-session access.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..core.errors import PolicyViolation, ValidationError


class PathPolicy:
    def __init__(self, roots: tuple[Path, ...], max_file_bytes: int) -> None:
        if not roots:
            raise ValidationError("At least one authorized file root is required")
        self.roots: list[Path] = [root.resolve() for root in roots]
        self.session_roots: dict[str, Path] = {}  # session_id → worktree root
        self.max_file_bytes = max_file_bytes

    # ── Dynamic root management ──────────────────────────────────────────

    def add_root(self, path: str | Path, *, session_id: str | None = None) -> Path:
        """Dynamically add an authorized root (e.g. worktree path after workspace_create).

        If session_id is provided, the root is stored in session_roots for
        per-session relative-path resolution and cross-session access control.
        Returns the resolved path. Idempotent — does not duplicate.
        """
        resolved = Path(path).expanduser().resolve()
        if session_id:
            self.session_roots[session_id] = resolved
        if resolved not in self.roots:
            self.roots.append(resolved)
        return resolved

    def remove_root(self, path: str | Path, *, session_id: str | None = None) -> bool:
        """Remove a dynamically added root (e.g. after worktree cleanup).

        Returns True if removed, False if not found.
        """
        resolved = Path(path).expanduser().resolve()
        if session_id and session_id in self.session_roots:
            del self.session_roots[session_id]
        try:
            self.roots.remove(resolved)
            return True
        except ValueError:
            return False

    # ── Forbidden segments ───────────────────────────────────────────────

    @staticmethod
    def _has_forbidden_segment(path: Path) -> bool:
        parts = tuple(part.casefold() for part in path.parts)
        if "credentials" in parts:
            return True
        if any(part in {".ssh", ".aws", ".gnupg"} for part in parts):
            return True
        return any(
            parts[index] == "_" and parts[index + 1] == "zip"
            for index in range(len(parts) - 1)
        )

    # ── Authorization ────────────────────────────────────────────────────

    def _session_root(self, session_id: str | None) -> Path | None:
        """Return the worktree root for a session, or None."""
        if session_id and session_id in self.session_roots:
            return self.session_roots[session_id]
        return None

    def is_authorized(self, path: Path, *, session_id: str | None = None) -> bool:
        """Check if a path is within authorized roots.

        With session_id: checks the session's worktree root FIRST, then static roots.
        Without: checks static roots only.
        """
        try:
            resolved = path.resolve(strict=True)
        except (FileNotFoundError, OSError):
            return False
        if self._has_forbidden_segment(resolved):
            return False
        # Session worktree takes priority
        root = self._session_root(session_id)
        if root is not None and resolved.is_relative_to(root):
            return True
        return any(resolved.is_relative_to(r) for r in self.roots)

    def resolve(
        self,
        raw_path: str,
        *,
        expect: str = "file",
        session_id: str | None = None,
    ) -> Path:
        """Resolve and authorize a path.

        Relative path resolution (in priority order):
        1. Session worktree root (if session_id and worktree registered)
        2. BOSSCORE_WORKSPACE (canonical repo)
        3. Rejected if neither available

        Absolute paths are authorized against the session root first,
        then static roots. Cross-session worktree access is blocked.
        """
        candidate = Path(raw_path).expanduser()

        # ── Relative path — resolve against session worktree or workspace ─
        if not candidate.is_absolute():
            root = self._session_root(session_id)
            if root is not None:
                candidate = root / candidate
            else:
                workspace = os.getenv("BOSSCORE_WORKSPACE", "")
                if workspace:
                    candidate = Path(workspace) / candidate
                else:
                    raise PolicyViolation(
                        "Relative path requires session worktree or BOSSCORE_WORKSPACE",
                        details={"path": raw_path, "session_id": session_id},
                    )

        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValidationError(f"Path not found: {candidate}") from exc

        if self._has_forbidden_segment(resolved):
            raise PolicyViolation("This path belongs to a protected credentials area")

        # ── Session-aware authorization ───────────────────────────────
        if not self.is_authorized(resolved, session_id=session_id):
            raise PolicyViolation(
                "Path is outside authorized roots",
                details={
                    "path": str(resolved),
                    "roots": [str(r) for r in self.roots],
                    "session_id": session_id,
                },
            )
        if expect == "file" and not resolved.is_file():
            raise ValidationError(f"Not a file: {resolved}")
        if expect == "directory" and not resolved.is_dir():
            raise ValidationError(f"Not a directory: {resolved}")
        if resolved.is_file() and resolved.stat().st_size > self.max_file_bytes:
            raise PolicyViolation(
                "File exceeds the configured size limit",
                details={
                    "size": resolved.stat().st_size,
                    "max_file_bytes": self.max_file_bytes,
                },
            )
        return resolved
