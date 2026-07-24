"""MCP tool contracts for document services."""
from __future__ import annotations

from typing import Any

from ..core.registry import ToolSpec, object_schema
from .service import DocumentService

STR = {"type": "string"}
INT = {"type": "integer", "minimum": 1}
OBJ = {"type": "object"}


class DocumentProvider:
    def __init__(self, service: DocumentService) -> None:
        self.service = service

    def specs(self) -> list[ToolSpec]:
        async def read_file(args: dict[str, Any]):
            return await self.service.read(args["path"], args.get("limit"))

        async def read_image(args: dict[str, Any]):
            return await self.service.image_data(args["path"])

        async def convert_to_markdown(args: dict[str, Any]):
            return await self.service.convert(args["path"], args.get("limit"))

        async def list_directory(args: dict[str, Any]):
            return await self.service.list_directory(args["path"], args.get("limit"))

        async def get_file_info(args: dict[str, Any]):
            return await self.service.info(args["path"])

        async def search_in_file(args: dict[str, Any]):
            return await self.service.search(args["path"], args["pattern"], args.get("limit"))

        def spec(name, description, handler, properties, required):
            return ToolSpec(
                name=name,
                description=description,
                input_schema=object_schema(properties, required),
                handler=handler,
                output_schema=OBJ,
                read_only=True,
                destructive=False,
                idempotent=True,
                open_world=False,
            )

        return [
            spec("read_file", "Read and extract an authorized local document", read_file, {"path": STR, "limit": INT}, ["path"]),
            spec("read_image", "Return an authorized local image as a data URL", read_image, {"path": STR}, ["path"]),
            spec("convert_to_markdown", "Convert an authorized document to Markdown", convert_to_markdown, {"path": STR, "limit": INT}, ["path"]),
            spec("list_directory", "List an authorized local directory", list_directory, {"path": STR, "limit": INT}, ["path"]),
            spec("get_file_info", "Get metadata for an authorized local path", get_file_info, {"path": STR}, ["path"]),
            spec("search_in_file", "Search within an authorized local document", search_in_file, {"path": STR, "pattern": STR, "limit": INT}, ["path", "pattern"]),
        ]

