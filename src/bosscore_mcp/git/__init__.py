"""Safe Git operations without shell injection."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ..core.errors import PolicyViolation, UpstreamError, ValidationError
from ..core.registry import ToolSpec, object_schema

STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}

SENSITIVE_PATTERNS = frozenset({
    ".env", "wp-config.php", "*.pem", "*.key", "*.p12", "*.pfx",
    "id_rsa", "id_ed25519", "auth.json", "secrets.*",
    "credentials/", "_/zip/",
})


def _git(*args: str, cwd: Path, timeout: int = 30, capture: bool = True) -> subprocess.CompletedProcess:
    """Run git with argument list (never shell)."""
    cmd = ["git", *args]
    kw: dict[str, Any] = {"cwd": str(cwd), "timeout": timeout}
    if capture:
        kw.update({"capture_output": True, "text": True})
    try:
        result = subprocess.run(cmd, **kw)
    except subprocess.TimeoutExpired as exc:
        raise UpstreamError(f"Git command timed out: {' '.join(args)}") from exc
    except FileNotFoundError:
        raise UpstreamError("Git executable not found")
    return result


class GitProvider:
    def __init__(
        self,
        repo_path: Path,
        *,
        branch: str = "master",
        remote: str = "origin",
        allowlist: tuple[str, ...] = (),
    ) -> None:
        self.repo_path = repo_path.resolve()
        self.branch = branch
        self.remote = remote
        self.allowlist = frozenset(allowlist)

        if not (self.repo_path / ".git").is_dir():
            raise ValidationError(f"Not a git repository: {self.repo_path}")

        if allowlist and str(self.repo_path) not in {str(Path(a).resolve()) for a in allowlist}:
            raise PolicyViolation("Repository not in allowlist")

    def _check_clean(self) -> None:
        r = _git("status", "--porcelain", cwd=self.repo_path)
        if r.returncode != 0:
            raise UpstreamError(f"git status failed: {r.stderr.strip()}")

    async def status(self, args: dict[str, Any]) -> dict[str, Any]:
        r = _git("status", "--porcelain", "--branch", cwd=self.repo_path)
        if r.returncode != 0:
            raise UpstreamError(f"Git status failed: {r.stderr.strip()}")
        head = _git("rev-parse", "HEAD", cwd=self.repo_path)
        return {
            "repo": str(self.repo_path),
            "branch": self.branch,
            "head_sha": head.stdout.strip()[:8] if head.returncode == 0 else "unknown",
            "status": r.stdout.strip()[:5000] if r.stdout else "clean",
            "dirty": bool(r.stdout.strip()),
        }

    async def diff(self, args: dict[str, Any]) -> dict[str, Any]:
        staged = bool(args.get("staged", False))
        cmd_args = ["diff", "--cached"] if staged else ["diff"]
        cmd_args.append(f"--unified={min(int(args.get('context', 3)), 10)}")
        if "path" in args:
            cmd_args.append("--")
            cmd_args.append(args["path"])
        r = _git(*cmd_args, cwd=self.repo_path)
        return {
            "staged": staged,
            "diff": r.stdout[:args.get("max_chars", 10000)] if r.stdout else "",
            "truncated": len(r.stdout) > args.get("max_chars", 10000),
        }

    async def log(self, args: dict[str, Any]) -> dict[str, Any]:
        count = min(int(args.get("count", 10)), 50)
        r = _git("log", f"-{count}", "--oneline", "--no-decorate", cwd=self.repo_path)
        return {
            "commits": [line.strip() for line in r.stdout.strip().split("\n") if line.strip()],
            "count": count,
        }

    async def stage(self, args: dict[str, Any]) -> dict[str, Any]:
        paths = args.get("paths", [])
        if not paths:
            raise ValidationError("At least one path is required for explicit staging")

        resolved: list[str] = []
        for p in paths:
            full = (self.repo_path / p).resolve()
            if not str(full).startswith(str(self.repo_path)):
                raise PolicyViolation(f"Path outside repository: {p}")
            if any(pattern in str(full) for pattern in SENSITIVE_PATTERNS):
                raise PolicyViolation(f"Cannot stage sensitive file: {p}")
            resolved.append(p)

        r = _git("add", "--", *resolved, cwd=self.repo_path)
        if r.returncode != 0:
            raise UpstreamError(f"git add failed: {r.stderr.strip()}")
        return {"staged": resolved, "count": len(resolved)}

    async def commit(self, args: dict[str, Any]) -> dict[str, Any]:
        message = args.get("message", "")
        if not message or not message.strip():
            raise ValidationError("Commit message is required")
        if len(message) > 500:
            raise ValidationError("Commit message too long (max 500 chars)")

        expected_sha = args.get("expected_head_sha", "")
        if expected_sha:
            r = _git("rev-parse", "HEAD", cwd=self.repo_path)
            current = r.stdout.strip()
            if current != expected_sha:
                raise PolicyViolation(
                    "HEAD SHA mismatch",
                    details={"expected": expected_sha[:8], "actual": current[:8]},
                )

        r = _git("commit", "-m", message, cwd=self.repo_path)
        if r.returncode != 0:
            raise UpstreamError(f"git commit failed: {r.stderr.strip()}")
        head = _git("rev-parse", "HEAD", cwd=self.repo_path)
        return {"sha": head.stdout.strip()[:8] if head.returncode == 0 else "unknown", "message": message}

    async def push(self, args: dict[str, Any]) -> dict[str, Any]:
        expected_sha = args.get("expected_head_sha", "")
        if expected_sha:
            head = _git("rev-parse", "HEAD", cwd=self.repo_path)
            if head.stdout.strip() != expected_sha:
                raise PolicyViolation("HEAD SHA mismatch before push")

        branch = args.get("branch", self.branch) or self.branch
        if args.get("protected_branch") and branch == args["protected_branch"]:
            raise PolicyViolation(f"Cannot push directly to protected branch: {branch}")

        r = _git("push", self.remote, branch, cwd=self.repo_path, timeout=60)
        if r.returncode != 0:
            raise UpstreamError(f"git push failed: {r.stderr.strip()}")

        pushed = _git("rev-parse", "HEAD", cwd=self.repo_path)
        return {
            "pushed": r.returncode == 0,
            "sha": pushed.stdout.strip()[:8] if pushed.returncode == 0 else "unknown",
            "branch": branch,
            "remote": self.remote,
        }

    async def sync_check(self, args: dict[str, Any]) -> dict[str, Any]:
        """Check if local and remote are in sync."""
        _git("fetch", self.remote, cwd=self.repo_path, timeout=30)
        local = _git("rev-parse", "HEAD", cwd=self.repo_path)
        remote = _git("rev-parse", f"{self.remote}/{self.branch}", cwd=self.repo_path)
        return {
            "local_sha": local.stdout.strip()[:8] if local.returncode == 0 else "unknown",
            "remote_sha": remote.stdout.strip()[:8] if remote.returncode == 0 else "unknown",
            "in_sync": local.stdout.strip() == remote.stdout.strip(),
        }

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="boss_git_status", description="Show working tree status (never modifies)",
                input_schema=object_schema(), handler=self.status,
                output_schema=object_schema({"repo": STR, "branch": STR, "head_sha": STR, "status": STR, "dirty": BOOL}),
                read_only=True, required_scopes=("boss:git:read",),
            ),
            ToolSpec(
                name="boss_git_diff", description="Show working tree changes",
                input_schema=object_schema({"staged": BOOL, "path": STR, "context": INT, "max_chars": INT}),
                handler=self.diff,
                output_schema=object_schema({"staged": BOOL, "diff": STR, "truncated": BOOL}),
                read_only=True, required_scopes=("boss:git:read",),
            ),
            ToolSpec(
                name="boss_git_log", description="Show recent commit history",
                input_schema=object_schema({"count": INT}), handler=self.log,
                output_schema=object_schema({"commits": {"type": "array", "items": STR}, "count": INT}),
                read_only=True, required_scopes=("boss:git:read",),
            ),
            ToolSpec(
                name="boss_git_stage", description="Stage specific files for commit (never git add -A)",
                input_schema=object_schema({"paths": {"type": "array", "items": STR}}, ["paths"]),
                handler=self.stage,
                output_schema=object_schema({"staged": {"type": "array", "items": STR}, "count": INT}),
                required_scopes=("boss:git:write",), risk_level="medium",
            ),
            ToolSpec(
                name="boss_git_commit", description="Create a commit with a message (no shell injection)",
                input_schema=object_schema({"message": STR, "expected_head_sha": STR}, ["message"]),
                handler=self.commit,
                output_schema=object_schema({"sha": STR, "message": STR}),
                required_scopes=("boss:git:write",), risk_level="medium",
            ),
            ToolSpec(
                name="boss_git_push", description="Push commits to remote (protected branches blocked)",
                input_schema=object_schema({"expected_head_sha": STR, "branch": STR, "protected_branch": STR}),
                handler=self.push,
                output_schema=object_schema({"pushed": BOOL, "sha": STR, "branch": STR, "remote": STR}),
                required_scopes=("boss:git:write",), risk_level="high", destructive=True,
            ),
            ToolSpec(
                name="boss_git_sync_check", description="Check if local branch is synchronized with remote",
                input_schema=object_schema(), handler=self.sync_check,
                output_schema=object_schema({"local_sha": STR, "remote_sha": STR, "in_sync": BOOL}),
                read_only=True, required_scopes=("boss:git:read",),
            ),
        ]
