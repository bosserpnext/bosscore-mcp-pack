"""Protocol-independent document extraction service with lazy backends."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

from ..core.errors import ConfigurationError, UpstreamError, ValidationError
from .policy import PathPolicy


class DocumentService:
    def __init__(
        self,
        policy: PathPolicy,
        *,
        max_output_chars: int,
        ollama_url: str,
        tesseract_command: str,
    ) -> None:
        self.policy = policy
        self.max_output_chars = max_output_chars
        self.ollama_url = ollama_url
        self.tesseract_command = tesseract_command
        self._markdown = None
        self._whisper = None

    @staticmethod
    def guess_type(path: Path) -> str:
        extension = path.suffix.casefold()
        groups = {
            "pdf": {".pdf"},
            "office": {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"},
            "image": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"},
            "audio": {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".opus", ".wma"},
            "video": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts"},
            "text": {".md", ".txt", ".csv", ".json", ".html", ".htm", ".xml", ".svg", ".py", ".js", ".ts", ".css", ".tsx", ".jsx", ".mjs", ".php", ".sh", ".yaml", ".yml", ".toml", ".ini"},
        }
        for kind, extensions in groups.items():
            if extension in extensions:
                return kind
        return "unknown"

    def _limit(self, requested: Any, default: int = 5000) -> int:
        try:
            value = int(requested if requested is not None else default)
        except (TypeError, ValueError) as exc:
            raise ValidationError("limit must be an integer") from exc
        return max(1, min(value, self.max_output_chars))

    def _markitdown(self):
        if self._markdown is None:
            try:
                from markitdown import MarkItDown
            except ImportError as exc:
                raise ConfigurationError(
                    "Document conversion requires the 'documents' dependency group"
                ) from exc
            self._markdown = MarkItDown()
        return self._markdown

    def _pillow(self):
        try:
            from PIL import Image
        except ImportError as exc:
            raise ConfigurationError(
                "Image support requires the 'documents' dependency group"
            ) from exc
        return Image

    async def _ollama_vision(self, path: Path) -> str:
        if path.stat().st_size > 20 * 1024 * 1024:
            return ""
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120)) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": "minicpm-v:latest",
                        "prompt": "Décris cette image en français, de façon précise et concise.",
                        "images": [encoded],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                return response.json().get("response", "").strip()
        except (httpx.HTTPError, ValueError):
            return ""

    def _ocr_image(self, image) -> str:
        try:
            import pytesseract
        except ImportError:
            return ""
        if not Path(self.tesseract_command).exists():
            return ""
        pytesseract.pytesseract.tesseract_cmd = self.tesseract_command
        try:
            return pytesseract.image_to_string(image, lang="fra+eng").strip()
        except Exception:
            return ""

    def _load_whisper(self):
        if self._whisper is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ConfigurationError(
                    "Transcription requires the 'audio' dependency group"
                ) from exc
            self._whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
        return self._whisper

    def _transcribe(self, path: Path) -> str:
        model = self._load_whisper()
        segments, _ = model.transcribe(str(path), language="fr", beam_size=5)
        return " ".join(segment.text for segment in segments).strip()

    async def read(self, raw_path: str, requested_limit: Any = None) -> dict[str, Any]:
        path = self.policy.resolve(raw_path)
        limit = self._limit(requested_limit)
        kind = self.guess_type(path)
        size = path.stat().st_size
        warnings: list[str] = []

        if kind == "text" or kind == "unknown":
            content = path.read_text(encoding="utf-8", errors="replace")[:limit]
            return self._result(path, kind, content, warnings)

        if kind == "pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise ConfigurationError(
                    "PDF support requires the 'documents' dependency group"
                ) from exc
            reader = PdfReader(str(path))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
            if not text:
                try:
                    text = self._markitdown().convert(str(path)).text_content.strip()
                except Exception:
                    warnings.append("No extractable text found; scanned PDF OCR is not yet available page-by-page.")
            return self._result(path, kind, text[:limit], warnings, pages=len(reader.pages))

        if kind == "office":
            text = self._markitdown().convert(str(path)).text_content
            return self._result(path, kind, text[:limit], warnings)

        if kind == "image":
            Image = self._pillow()
            with Image.open(path) as image:
                metadata = {"width": image.width, "height": image.height, "format": image.format}
                ocr = await asyncio.to_thread(self._ocr_image, image.copy())
            vision = await self._ollama_vision(path)
            content_parts = []
            if vision:
                content_parts.append(f"--- Description ---\n{vision}")
            else:
                warnings.append("Ollama vision unavailable or returned no description.")
            if ocr:
                content_parts.append(f"--- OCR ---\n{ocr}")
            return self._result(path, kind, "\n\n".join(content_parts)[:limit], warnings, **metadata)

        if kind == "audio":
            text = await asyncio.to_thread(self._transcribe, path)
            return self._result(path, kind, text[:limit], warnings)

        if kind == "video":
            try:
                from moviepy import VideoFileClip
            except ImportError as exc:
                raise ConfigurationError(
                    "Video transcription requires the 'audio' dependency group"
                ) from exc
            temporary = Path(tempfile.gettempdir()) / f"bosscore-mcp-{os.getpid()}-{path.stem}.wav"
            clip = None
            try:
                clip = VideoFileClip(str(path))
                if clip.audio is None:
                    warnings.append("Video has no audio track.")
                    text = ""
                else:
                    clip.audio.write_audiofile(str(temporary), logger=None)
                    text = await asyncio.to_thread(self._transcribe, temporary)
            finally:
                if clip is not None:
                    clip.close()
                temporary.unlink(missing_ok=True)
            return self._result(path, kind, text[:limit], warnings)

        raise ValidationError(f"Unsupported document type: {kind}")

    def _result(self, path: Path, kind: str, content: str, warnings: list[str], **metadata):
        return {
            "document": {
                "name": path.name,
                "path": str(path),
                "kind": kind,
                "size": path.stat().st_size,
                **metadata,
            },
            "content": content,
            "truncated": len(content) >= self.max_output_chars,
            "warnings": warnings,
        }

    async def image_data(self, raw_path: str) -> dict[str, Any]:
        path = self.policy.resolve(raw_path)
        if self.guess_type(path) != "image":
            raise ValidationError("read_image accepts image files only")
        if path.stat().st_size > 5 * 1024 * 1024:
            raise ValidationError("read_image is limited to 5 MiB")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {
            "path": str(path),
            "mime_type": mime,
            "size": path.stat().st_size,
            "data_url": f"data:{mime};base64,{encoded}",
        }

    async def convert(self, raw_path: str, requested_limit: Any = None) -> dict[str, Any]:
        path = self.policy.resolve(raw_path)
        limit = self._limit(requested_limit, 10000)
        text = self._markitdown().convert(str(path)).text_content
        return {
            "path": str(path),
            "markdown": text[:limit],
            "truncated": len(text) > limit,
        }

    async def list_directory(self, raw_path: str, requested_limit: Any = None) -> dict[str, Any]:
        path = self.policy.resolve(raw_path, expect="directory")
        limit = min(self._limit(requested_limit, 100), 1000)
        entries = []
        for entry in sorted(path.iterdir(), key=lambda item: item.name.casefold()):
            try:
                if not self.policy.is_authorized(entry):
                    continue
                entries.append(
                    {
                        "name": entry.name,
                        "type": "directory" if entry.is_dir() else "file",
                        "size": entry.stat().st_size if entry.is_file() else 0,
                    }
                )
            except OSError:
                continue
        return {"path": str(path), "count": len(entries), "entries": entries[:limit], "truncated": len(entries) > limit}

    async def info(self, raw_path: str) -> dict[str, Any]:
        path = self.policy.resolve(raw_path, expect="any")
        stat = path.stat()
        return {
            "name": path.name,
            "path": str(path),
            "size": stat.st_size,
            "type": self.guess_type(path) if path.is_file() else "directory",
            "extension": path.suffix,
            "modified": stat.st_mtime,
            "is_dir": path.is_dir(),
        }

    async def search(self, raw_path: str, pattern: str, requested_limit: Any = None):
        path = self.policy.resolve(raw_path)
        if not pattern:
            raise ValidationError("pattern cannot be empty")
        limit = min(self._limit(requested_limit, 20), 500)
        if self.guess_type(path) in {"text", "unknown"}:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            matches = [
                {"line": index, "text": line}
                for index, line in enumerate(lines, 1)
                if pattern.casefold() in line.casefold()
            ]
        else:
            converted = await self.convert(str(path), self.max_output_chars)
            lines = converted["markdown"].splitlines()
            matches = [
                {"line": index, "text": line}
                for index, line in enumerate(lines, 1)
                if pattern.casefold() in line.casefold()
            ]
        return {"path": str(path), "matches": len(matches), "results": matches[:limit], "truncated": len(matches) > limit}
