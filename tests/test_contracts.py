from __future__ import annotations

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


def test_wordpress_contract_exposes_expected_surface():
    provider = WordPressProvider(FakeWordPressClient())
    actual = {spec.name for spec in provider.specs()}
    required = {
        "wp_list_pages",
        "wp_get_page",
        "wp_create_page",
        "wp_update_page",
        "wp_delete_page",
        "wp_list_media",
        "wp_upload_media",
        "wp_list_users",
        "wp_create_user",
        "wp_delete_user",
        "wp_raw_request",
    }
    assert required <= actual
    assert len(actual) == 55


def test_document_contract_exposes_exact_surface(tmp_path):
    service = DocumentService(
        PathPolicy((tmp_path,), 1024),
        max_output_chars=5000,
        ollama_url="http://localhost:11434",
        tesseract_command="missing",
    )
    actual = {spec.name for spec in DocumentProvider(service).specs()}
    assert actual == {
        "read_file",
        "list_directory",
        "search_in_file",
        "get_file_info",
        "convert_to_markdown",
        "read_image",
    }


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
