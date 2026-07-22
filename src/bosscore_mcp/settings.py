"""Environment-backed configuration without embedded secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .core.errors import ConfigurationError


def _split_paths(value: str) -> tuple[Path, ...]:
    return tuple(
        Path(part.strip()).expanduser().resolve()
        for part in value.split(os.pathsep)
        if part.strip()
    )


@dataclass(frozen=True, slots=True)
class Settings:
    profile: str
    wordpress_url: str
    wordpress_username: str
    wordpress_password: str
    file_roots: tuple[Path, ...]
    max_file_bytes: int
    max_output_chars: int
    ollama_url: str
    tesseract_command: str

    @classmethod
    def from_env(cls) -> "Settings":
        profile = os.getenv("BOSSCORE_MCP_PROFILE", "full").strip().lower()
        if profile not in {"wordpress", "files", "full"}:
            raise ConfigurationError(
                "BOSSCORE_MCP_PROFILE must be wordpress, files, or full"
            )
        wordpress_url = os.getenv("WORDPRESS_URL", "").rstrip("/")
        if wordpress_url:
            parsed = urlparse(wordpress_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ConfigurationError("WORDPRESS_URL must be an HTTP(S) URL")

        roots = _split_paths(os.getenv("BOSSCORE_FILE_ROOTS", ""))
        return cls(
            profile=profile,
            wordpress_url=wordpress_url,
            wordpress_username=os.getenv("WORDPRESS_USERNAME", ""),
            wordpress_password=os.getenv("WORDPRESS_APP_PASSWORD", ""),
            file_roots=roots,
            max_file_bytes=int(
                os.getenv("BOSSCORE_MAX_FILE_BYTES", str(100 * 1024 * 1024))
            ),
            max_output_chars=int(os.getenv("BOSSCORE_MAX_OUTPUT_CHARS", "50000")),
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
            tesseract_command=os.getenv(
                "TESSERACT_CMD",
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            ),
        )

    def require_wordpress(self) -> None:
        missing = []
        if not self.wordpress_url:
            missing.append("WORDPRESS_URL")
        if not self.wordpress_username:
            missing.append("WORDPRESS_USERNAME")
        if not self.wordpress_password:
            missing.append("WORDPRESS_APP_PASSWORD")
        if missing:
            raise ConfigurationError(
                "Missing WordPress configuration",
                details={"missing": missing},
            )

    def require_file_roots(self) -> None:
        if not self.file_roots:
            raise ConfigurationError(
                "BOSSCORE_FILE_ROOTS must contain at least one authorized root"
            )

