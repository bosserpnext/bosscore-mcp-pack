from __future__ import annotations

import asyncio

import pytest

from bosscore_mcp.documents.policy import PathPolicy
from bosscore_mcp.documents.service import DocumentService


@pytest.fixture
def service(tmp_path):
    return DocumentService(
        PathPolicy((tmp_path,), 1024 * 1024),
        max_output_chars=1000,
        ollama_url="http://localhost:11434",
        tesseract_command="missing",
    )


def test_reads_utf8_text(service, tmp_path):
    document = tmp_path / "note.md"
    document.write_text("Bonjour BOSSCORE", encoding="utf-8")
    result = asyncio.run(service.read(str(document), 100))
    assert result["document"]["kind"] == "text"
    assert result["content"] == "Bonjour BOSSCORE"


def test_search_returns_line_numbers(service, tmp_path):
    document = tmp_path / "note.txt"
    document.write_text("alpha\nBOSSCORE\nomega\n", encoding="utf-8")
    result = asyncio.run(service.search(str(document), "bosscore", 20))
    assert result["matches"] == 1
    assert result["results"][0] == {"line": 2, "text": "BOSSCORE"}


def test_directory_listing_hides_protected_children(service, tmp_path):
    (tmp_path / "visible.txt").write_text("ok", encoding="utf-8")
    protected = tmp_path / "credentials"
    protected.mkdir()
    (protected / "secret.txt").write_text("no", encoding="utf-8")
    result = asyncio.run(service.list_directory(str(tmp_path), 100))
    assert [entry["name"] for entry in result["entries"]] == ["visible.txt"]
