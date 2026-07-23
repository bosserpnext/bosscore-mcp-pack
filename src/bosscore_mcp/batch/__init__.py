"""Batch tool — concurrent execution of multiple tools in a single call.

Usage from an LLM:
  Call boss_batch with operations=[{name, arguments}, ...] to run them
  concurrently. Each operation is a regular tool call dispatched through
  the same ToolRegistry as a normal single-tool call.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from ..core.errors import ValidationError
from ..core.registry import ToolRegistry, ToolSpec, object_schema

STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
NUMBER = {"type": "number"}


class BatchProvider:
    """Provider for the boss_batch tool.

    Holds a reference to the registry so it can dispatch sub-operations
    through the same tool resolution as single calls.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def batch(self, args: dict[str, Any]) -> dict[str, Any]:
        """Execute multiple tools concurrently.

        Input:
          operations: [{name: str, arguments?: object}]
          max_concurrent: int (default 10)
          timeout_seconds: int (default 60)
          stop_on_error: bool (default false)

        Returns per-operation results tagged with tool name, success/error,
        and duration.
        """
        operations = args.get("operations", [])
        if not isinstance(operations, list) or not operations:
            raise ValidationError(
                "operations must be a non-empty array of {name, arguments}",
                details={"received_type": type(operations).__name__},
            )

        max_concurrent = min(max(int(args.get("max_concurrent", 10)), 1), 50)
        timeout_seconds = min(max(int(args.get("timeout_seconds", 60)), 1), 300)
        stop_on_error = bool(args.get("stop_on_error", False))

        semaphore = asyncio.Semaphore(max_concurrent)
        stop_event = asyncio.Event()  # signaled when stop_on_error fires

        async def _run_one(op: dict[str, Any]) -> dict[str, Any]:
            """Execute a single operation with concurrency and timeout."""
            tool_name = op.get("name", "")
            if not isinstance(tool_name, str) or not tool_name:
                return {
                    "name": str(tool_name),
                    "success": False,
                    "error": "operation must have a non-empty 'name' field",
                    "duration_ms": 0,
                    "status": "invalid",
                }

            # Check stop_on_error BEFORE acquiring semaphore
            if stop_on_error and stop_event.is_set():
                return {
                    "name": tool_name,
                    "success": False,
                    "status": "skipped",
                    "reason": "previous operation failed (stop_on_error)",
                    "duration_ms": 0,
                }

            async with semaphore:
                # Double-check after semaphore wait (another task may have
                # set the stop_event while we were waiting)
                if stop_on_error and stop_event.is_set():
                    return {
                        "name": tool_name,
                        "success": False,
                        "status": "skipped",
                        "reason": "previous operation failed (stop_on_error)",
                        "duration_ms": 0,
                    }

                t0 = time.perf_counter()
                tool_args = op.get("arguments", {})
                if not isinstance(tool_args, dict):
                    tool_args = {}

                try:
                    result = await asyncio.wait_for(
                        self._registry.call(tool_name, tool_args),
                        timeout=timeout_seconds,
                    )
                    elapsed = (time.perf_counter() - t0) * 1000
                    return {
                        "name": tool_name,
                        "success": True,
                        "result": result,
                        "duration_ms": round(elapsed, 2),
                        "status": "completed",
                    }
                except asyncio.TimeoutError:
                    elapsed = (time.perf_counter() - t0) * 1000
                    if stop_on_error:
                        stop_event.set()
                    return {
                        "name": tool_name,
                        "success": False,
                        "error": f"timed out after {timeout_seconds}s",
                        "duration_ms": round(elapsed, 2),
                        "status": "timeout",
                    }
                except Exception as exc:
                    elapsed = (time.perf_counter() - t0) * 1000
                    if stop_on_error:
                        stop_event.set()
                    return {
                        "name": tool_name,
                        "success": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "duration_ms": round(elapsed, 2),
                        "status": "error",
                    }

        tasks = [_run_one(op) for op in operations]
        results = await asyncio.gather(*tasks)

        summary = {
            "total": len(results),
            "completed": sum(1 for r in results if r.get("status") == "completed"),
            "succeeded": sum(1 for r in results if r.get("success")),
            "failed": sum(1 for r in results if not r.get("success")),
            "skipped": sum(1 for r in results if r.get("status") == "skipped"),
        }

        return {
            "summary": summary,
            "operations": results,
        }

    def specs(self) -> list[ToolSpec]:
        """Return the tool spec for boss_batch."""
        return [
            ToolSpec(
                name="boss_batch",
                description=(
                    "Execute multiple tools concurrently in a single call. "
                    "Accepts an array of operations (each with 'name' and optional 'arguments'). "
                    "Runs them in parallel up to max_concurrent. "
                    "Useful for batching independent read operations or parallel writes. "
                    "Supports configurable timeout and optional stop-on-first-error."
                ),
                input_schema=object_schema(
                    properties={
                        "operations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": (
                                            "Name of the tool to call "
                                            "(e.g. boss_health_check, wp_list_posts)"
                                        ),
                                    },
                                    "arguments": {
                                        "type": "object",
                                        "description": (
                                            "Arguments to pass to the tool (optional, default {})"
                                        ),
                                        "additionalProperties": True,
                                    },
                                },
                                "required": ["name"],
                            },
                            "minItems": 1,
                            "maxItems": 100,
                            "description": "Array of tool operations to execute concurrently",
                        },
                        "max_concurrent": {
                            "type": "integer",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50,
                            "description": "Maximum number of operations to run concurrently (default 10)",
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "default": 60,
                            "minimum": 1,
                            "maximum": 300,
                            "description": "Maximum seconds per operation (default 60)",
                        },
                        "stop_on_error": {
                            "type": "boolean",
                            "default": False,
                            "description": (
                                "If true, skip remaining operations when any operation fails "
                                "(default false — collect all results)"
                            ),
                        },
                    },
                    required=["operations"],
                ),
                handler=self.batch,
                output_schema=object_schema(
                    properties={
                        "summary": {
                            "type": "object",
                            "properties": {
                                "total": INT,
                                "completed": INT,
                                "succeeded": INT,
                                "failed": INT,
                                "skipped": INT,
                            },
                            "description": "Aggregate counts across all operations",
                        },
                        "operations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": STR,
                                    "success": BOOL,
                                    "status": STR,
                                    "result": {
                                        "description": "Tool-specific result if successful"
                                    },
                                    "error": STR,
                                    "duration_ms": NUMBER,
                                    "reason": STR,
                                },
                            },
                            "description": "Per-operation results in input order",
                        },
                    },
                ),
                read_only=False,
                idempotent=False,
            ),
        ]
