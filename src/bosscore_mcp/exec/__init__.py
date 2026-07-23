"""Sandboxed shell executor — plan/confirm/execute pattern.

Allows ChatGPT to run development commands safely:
  boss_exec_plan    → Show what would be executed (dry-run preview)
  boss_exec_confirm → Generate a confirmation token linked to the plan
  boss_exec_run     → Execute with valid token (one-shot, timeout, bounded output)
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..core.errors import PolicyViolation, UpstreamError, ValidationError
from ..core.registry import ToolSpec, object_schema

STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}

# ── Security configuration ──────────────────────────────────────────────────────
ALLOWED_COMMANDS: frozenset[str] = frozenset(
    c.strip() for c in os.getenv(
        "BOSSCORE_EXEC_ALLOWED_COMMANDS",
        "composer,git,php,wp,ls,pwd,cat,head,tail,grep,find,which,python3,python,node,npm,npx,pm2,curl,wget,tar,zip,unzip,mkdir,cp,mv,rm,chmod,chown",
    ).split(",") if c.strip()
)

ALLOWED_PATHS: tuple[Path, ...] = tuple(
    Path(p.strip()).resolve()
    for p in os.getenv("BOSSCORE_EXEC_ALLOWED_PATHS", os.getenv("BOSSCORE_WORKSPACE", "/home/bomoja/repos/companies")).split(os.pathsep)
    if p.strip() and Path(p.strip()).is_dir()
)

BLOCKED_PATTERNS: frozenset[str] = frozenset({
    ">/dev/null", "2>&1", "&&", "||", "`", "$(", "${", ";", "|", "&",
    "sudo", "su ", "passwd", "chown root", "chmod 777", "rm -rf /",
    "> /etc", "> ~/.ssh", "/etc/passwd", "/etc/shadow",
})

MAX_OUTPUT_CHARS = int(os.getenv("BOSSCORE_EXEC_MAX_OUTPUT", "50000"))
EXEC_TIMEOUT = int(os.getenv("BOSSCORE_EXEC_TIMEOUT", "60"))
PLAN_TTL = int(os.getenv("BOSSCORE_EXEC_PLAN_TTL", "120"))  # 2 min

_PLANS: dict[str, dict[str, Any]] = {}


class ExecProvider:
    """Sandboxed command executor with plan/confirm/execute."""

    def __init__(self) -> None:
        self.allowed_cmds = ALLOWED_COMMANDS
        self.allowed_paths = ALLOWED_PATHS
        self.workspace = Path(os.getenv("BOSSCORE_WORKSPACE", "/home/bomoja/repos/companies"))

    def _validate_command(self, command: str) -> list[str]:
        """Parse and validate a command string. Returns argv list."""
        cmd = command.strip()
        if not cmd:
            raise ValidationError("Command is empty")

        # Block dangerous patterns
        cmd_lower = cmd.lower()
        for pattern in BLOCKED_PATTERNS:
            if pattern.lower() in cmd_lower:
                raise PolicyViolation(
                    f"Blocked pattern detected: {pattern}",
                    details={"pattern": pattern},
                )

        # Split into argv
        import shlex
        try:
            argv = shlex.split(cmd)
        except ValueError as exc:
            raise ValidationError(f"Cannot parse command: {exc}")

        if not argv:
            raise ValidationError("Command is empty after parsing")

        # Check base command is allowed
        base = os.path.basename(argv[0]) if "/" in argv[0] else argv[0]
        if base not in self.allowed_cmds:
            raise PolicyViolation(
                f"Command not allowed: {base}",
                details={"command": base, "allowed": sorted(self.allowed_cmds)},
            )

        return argv

    def _resolve_cwd(self, cwd: str) -> Path:
        """Resolve working directory, ensuring it's within allowed paths."""
        if not cwd:
            return self.workspace
        resolved = Path(cwd).expanduser().resolve()
        if not any(str(resolved).startswith(str(p)) for p in self.allowed_paths):
            raise PolicyViolation(
                f"Working directory outside allowed paths: {cwd}",
                details={"cwd": str(resolved), "allowed": [str(p) for p in self.allowed_paths]},
            )
        return resolved

    async def plan(self, args: dict[str, Any]) -> dict[str, Any]:
        """Preview a command before execution — shows what will run."""
        command = args.get("command", "").strip()
        if not command:
            raise ValidationError("command is required")

        cwd = self._resolve_cwd(args.get("cwd", ""))
        argv = self._validate_command(command)

        plan_id = f"exec-{uuid4().hex[:8]}"
        plan = {
            "plan_id": plan_id,
            "command": command,
            "argv": argv,
            "cwd": str(cwd),
            "timeout": min(int(args.get("timeout", EXEC_TIMEOUT)), 300),
            "status": "draft",
            "expires_at": int(time.time()) + PLAN_TTL,
            "created_at": int(time.time()),
        }
        _PLANS[plan_id] = plan

        return {
            "plan_id": plan_id,
            "command": command,
            "cwd": str(cwd),
            "timeout_seconds": plan["timeout"],
            "expires_in_seconds": PLAN_TTL,
            "confirm_token": hashlib.sha256(f"{plan_id}:execute".encode()).hexdigest()[:8],
        }

    async def confirm(self, args: dict[str, Any]) -> dict[str, Any]:
        """Generate a confirmation token for a planned command."""
        plan_id = args.get("plan_id", "")
        if not plan_id or plan_id not in _PLANS:
            raise ValidationError("Invalid or expired plan_id. Call boss_exec_plan first.")

        plan = _PLANS[plan_id]
        if plan["status"] != "draft":
            raise ValidationError(f"Plan already {plan['status']}")

        if int(time.time()) > plan["expires_at"]:
            plan["status"] = "expired"
            _PLANS.pop(plan_id, None)
            raise PolicyViolation("Plan has expired. Create a new plan.")

        confirm_token = hashlib.sha256(f"{plan_id}:execute".encode()).hexdigest()[:8]

        return {
            "plan_id": plan_id,
            "command": plan["command"],
            "confirm_token": confirm_token,
            "note": "Pass this token to boss_exec_run to execute.",
        }

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a confirmed command."""
        plan_id = args.get("plan_id", "")
        confirm_token = args.get("confirm_token", "")

        if not plan_id or plan_id not in _PLANS:
            raise ValidationError("Invalid or expired plan_id")

        plan = _PLANS[plan_id]
        if plan["status"] != "draft":
            raise ValidationError(f"Plan already {plan['status']}")

        if int(time.time()) > plan["expires_at"]:
            plan["status"] = "expired"
            _PLANS.pop(plan_id, None)
            raise PolicyViolation("Plan expired")

        expected = hashlib.sha256(f"{plan_id}:execute".encode()).hexdigest()[:8]
        if confirm_token != expected:
            raise PolicyViolation(
                "Confirmation token mismatch",
                details={"expected": expected, "got": confirm_token},
            )

        plan["status"] = "running"

        try:
            result = subprocess.run(
                plan["argv"],
                cwd=plan["cwd"],
                capture_output=True,
                text=True,
                timeout=plan["timeout"],
                shell=False,
                env={**os.environ, "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")},
            )
        except subprocess.TimeoutExpired as exc:
            plan["status"] = "timeout"
            raise UpstreamError(f"Command timed out after {plan['timeout']}s") from exc
        except Exception as exc:
            plan["status"] = "error"
            raise UpstreamError(f"Command failed: {exc}") from exc

        plan["status"] = "completed"
        _PLANS.pop(plan_id, None)

        stdout = result.stdout[:MAX_OUTPUT_CHARS] if result.stdout else ""
        stderr = result.stderr[:MAX_OUTPUT_CHARS] if result.stderr else ""

        return {
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated_stdout": len(result.stdout) > MAX_OUTPUT_CHARS if result.stdout else False,
            "truncated_stderr": len(result.stderr) > MAX_OUTPUT_CHARS if result.stderr else False,
            "command": plan["command"],
            "cwd": plan["cwd"],
        }

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="boss_exec_plan",
                description="Preview a shell command before execution. Shows what will run, where, and with what timeout. Returns a plan_id.",
                input_schema=object_schema(
                    {"command": STR, "cwd": STR, "timeout": INT},
                    ["command"],
                ),
                handler=self.plan,
                output_schema=object_schema({
                    "plan_id": STR, "command": STR, "cwd": STR,
                    "timeout_seconds": INT, "expires_in_seconds": INT, "confirm_token": STR,
                }),
                required_scopes=("boss:git:write", "boss:deploy:staging"),
                risk_level="high",
            ),
            ToolSpec(
                name="boss_exec_confirm",
                description="Generate a confirmation token for a planned command. The token must be passed to boss_exec_run.",
                input_schema=object_schema({"plan_id": STR}, ["plan_id"]),
                handler=self.confirm,
                output_schema=object_schema({"plan_id": STR, "command": STR, "confirm_token": STR}),
                required_scopes=("boss:git:write", "boss:deploy:staging"),
                risk_level="high",
            ),
            ToolSpec(
                name="boss_exec_run",
                description="Execute a confirmed command (safe: allowlist, no shell injection, bounded output, timeout).",
                input_schema=object_schema({"plan_id": STR, "confirm_token": STR}, ["plan_id", "confirm_token"]),
                handler=self.execute,
                output_schema=object_schema({
                    "exit_code": INT, "stdout": STR, "stderr": STR,
                    "truncated_stdout": BOOL, "truncated_stderr": BOOL,
                    "command": STR, "cwd": STR,
                }),
                required_scopes=("boss:git:write", "boss:deploy:staging"),
                risk_level="critical", destructive=True, supports_confirmation=True,
            ),
        ]
