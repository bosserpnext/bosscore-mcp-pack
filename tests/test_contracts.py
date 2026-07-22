from __future__ import annotations

import ast
from pathlib import Path

from bosscore_mcp.core.registry import ToolRegistry
from bosscore_mcp.documents.policy import PathPolicy
from bosscore_mcp.documents.provider import DocumentProvider
from bosscore_mcp.documents.service import DocumentService
from bosscore_mcp.wordpress.provider import WordPressProvider


class FakeWordPressClient:
    async def request(self, method, path, **kwargs):
        raise AssertionError("No HTTP request expected in contract tests")

    async def download_public(self, url, **kwargs):
        raise AssertionError("No download expected in contract tests")


def legacy_tool_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Tool":
            for keyword in node.keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    names.add(keyword.value.value)
    return names


def test_wordpress_contract_preserves_all_legacy_names():
    provider = WordPressProvider(FakeWordPressClient())
    actual = {spec.name for spec in provider.specs()}
    legacy = legacy_tool_names(
        Path(r"C:\Users\Takoudjou\.config\opencode\mcp-wordpress-bridge.py")
    )
    assert actual == legacy
    assert len(actual) == 55


def test_document_contract_preserves_all_legacy_names(tmp_path):
    service = DocumentService(
        PathPolicy((tmp_path,), 1024),
        max_output_chars=5000,
        ollama_url="http://localhost:11434",
        tesseract_command="missing",
    )
    actual = {spec.name for spec in DocumentProvider(service).specs()}
    legacy = legacy_tool_names(
        Path(r"C:\Users\Takoudjou\.config\opencode\mcp-file-reader.py")
    )
    assert actual == legacy
    assert len(actual) == 6


def test_combined_registry_has_61_unique_tools(tmp_path):
    registry = ToolRegistry()
    registry.extend(WordPressProvider(FakeWordPressClient()).specs())
    service = DocumentService(
        PathPolicy((tmp_path,), 1024),
        max_output_chars=5000,
        ollama_url="http://localhost:11434",
        tesseract_command="missing",
    )
    registry.extend(DocumentProvider(service).specs())
    assert len(registry.names) == 61
    assert len(set(registry.names)) == 61


def test_annotations_distinguish_read_and_destructive_tools():
    tools = {
        tool.name: tool
        for tool in WordPressProvider(FakeWordPressClient()).specs()
    }
    assert tools["wp_list_pages"].read_only is True
    assert tools["wp_delete_user"].destructive is True
    assert tools["wp_update_page"].idempotent is True
    assert tools["wp_upload_media"].open_world is True

