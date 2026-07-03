"""Tool registry + ToolResponse contract (Tools.md §12).

Every tool is a plain Python function that takes a DB session plus typed kwargs
and returns a JSON-serialisable payload (or raises ToolError). The registry
wraps each call with timing and the standard ToolResponse envelope, and exposes
Anthropic-compatible tool schemas so Claude can call them.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class ToolError(Exception):
    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        # code in DATA_NOT_FOUND | SYSTEM_UNAVAILABLE | INVALID_INPUT | PERMISSION_DENIED
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


@dataclass
class ToolSpec:
    tool_id: str
    name: str
    category: str
    description: str
    input_schema: dict
    func: Callable[..., Any]


REGISTRY: dict[str, ToolSpec] = {}


def tool(tool_id: str, name: str, category: str, description: str, input_schema: dict):
    """Decorator registering a function as a callable agent tool."""
    def wrap(fn: Callable[..., Any]):
        REGISTRY[name] = ToolSpec(tool_id, name, category, description, input_schema, fn)
        return fn
    return wrap


def run_tool(db, name: str, arguments: dict) -> dict:
    """Execute a tool by name, returning a ToolResponse dict."""
    started = time.perf_counter()
    spec = REGISTRY.get(name)
    if spec is None:
        return _envelope(False, None,
                         {"code": "INVALID_INPUT", "message": f"Unknown tool '{name}'"},
                         name, started)
    try:
        data = spec.func(db, **(arguments or {}))
        return _envelope(True, data, None, spec.tool_id, started)
    except ToolError as e:
        return _envelope(False, None,
                         {"code": e.code, "message": e.message, "details": e.details},
                         spec.tool_id, started)
    except Exception as e:  # noqa: BLE001 - surface unexpected failures to the agent
        return _envelope(False, None,
                         {"code": "SYSTEM_UNAVAILABLE", "message": str(e)},
                         spec.tool_id, started)


def _envelope(success, data, error, tool_id, started) -> dict:
    return {
        "success": success,
        "data": data,
        "error": error,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "tool_id": tool_id,
    }


def anthropic_schema(name: str) -> dict:
    spec = REGISTRY[name]
    return {
        "name": name,
        "description": f"[{spec.tool_id}] {spec.description}",
        "input_schema": spec.input_schema,
    }


def catalog() -> list[dict]:
    """Full tool catalogue for the UI toolkit view."""
    return [
        {"tool_id": s.tool_id, "name": n, "category": s.category,
         "description": s.description}
        for n, s in sorted(REGISTRY.items(), key=lambda kv: kv[1].tool_id)
    ]
