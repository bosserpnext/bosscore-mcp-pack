"""Filesystem authorization policy for document tools."""
from __future__ import annotations

from pathlib import Path

from ..core.errors import PolicyViolation, ValidationError


class PathPolicy:
    def __init__(self, roots: tuple[Path, ...], max_file_bytes: int) -> None:
        if not roots:
            raise ValidationError("At least one authorized file root is required")
        self.roots = tuple(root.resolve() for root in roots)
        self.max_file_bytes = max_file_bytes

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

    def is_authorized(self, path: Path) -> bool:
        try:
            resolved = path.resolve(strict=True)
        except (FileNotFoundError, OSError):
            return False
        return (
            not self._has_forbidden_segment(resolved)
            and any(resolved.is_relative_to(root) for root in self.roots)
        )

    def resolve(self, raw_path: str, *, expect: str = "file") -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise PolicyViolation("Only absolute paths are accepted")
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValidationError(f"Path not found: {candidate}") from exc

        if self._has_forbidden_segment(resolved):
            raise PolicyViolation("This path belongs to a protected credentials area")
        if not self.is_authorized(resolved):
            raise PolicyViolation(
                "Path is outside authorized roots",
                details={"path": str(resolved), "roots": [str(root) for root in self.roots]},
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
