#!/usr/bin/env python3
"""Stdio JSON-RPC 2.0 MCP server for Gravity persistent hierarchical memory."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = PLUGIN_ROOT / "skills" / "memory-sync" / "scripts"
SERVER_INFO = {"name": "gravity-memory", "version": "1.1.0"}
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18"}
HYDRATE_EMPTY_MSG = (
    "No .agents/memory initialized yet; call memory_reindex or memory_checkpoint."
)


def _tool(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    """Build an MCP tool definition with a strict JSON Schema input object."""
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {"workspace": {"type": "string", "description": "Workspace root path."}, **properties},
            "required": required,
            "additionalProperties": False,
        },
    }


TOOLS: list[dict[str, Any]] = [
    _tool("memory_hydrate", "Return compact L2 project memory brief for a workspace.", {}, ["workspace"]),
    _tool(
        "symbol_lookup",
        "Look up architectural-priority ranked file:start-end symbols (supports format='toon' for token savings).",
        {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "default": 10},
            "format": {"type": "string", "enum": ["json", "toon"], "default": "json"},
        },
        ["workspace", "query"],
    ),
    _tool(
        "memory_search",
        "BM25 + path-weighted search across shards, LESSONS.md, and docs (supports format='toon').",
        {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "default": 8},
            "format": {"type": "string", "enum": ["json", "toon"], "default": "json"},
        },
        ["workspace", "query"],
    ),
    _tool(
        "memory_checkpoint",
        "Save L2 state and optional L3 shard note with automatic decision-conflict check.",
        {
            "active_task": {"type": "string"},
            "status": {"type": "string"},
            "verified_tests": {"type": ["string", "array"]},
            "blockers": {"type": "array", "items": {"type": "string"}},
            "next_steps": {"type": "array", "items": {"type": "string"}},
            "note_shard": {"type": "string"},
            "note_title": {"type": "string"},
            "note_body": {"type": "string"},
        },
        ["workspace"],
    ),
    _tool(
        "memory_reindex",
        "Run fast full or incremental L1+L3 workspace re-index.",
        {"paths": {"type": "array", "items": {"type": "string"}}},
        ["workspace"],
    ),
    _tool(
        "memory_lesson",
        "Record or query 30-day decaying experiential lessons (useful, dead_end, corrected).",
        {
            "action": {"type": "string", "enum": ["record", "list"], "default": "list"},
            "outcome": {"type": "string", "enum": ["useful", "dead_end", "corrected"]},
            "query": {"type": "string"},
            "paths": {"type": "array", "items": {"type": "string"}},
            "correction": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "default": 10},
            "format": {"type": "string", "enum": ["json", "toon"], "default": "json"},
        },
        ["workspace"],
    ),
    _tool(
        "context_budget",
        "Inspect real-time conversation context token volume, usage %, and active isolated task worktrees.",
        {
            "conversation_id": {"type": "string", "description": "Optional conversation ID."},
            "max_tokens": {"type": "integer", "default": 200000, "description": "Maximum context token capacity."},
            "generate_html": {"type": "boolean", "default": False, "description": "Generate standalone interactive HTML cockpit."},
        },
        ["workspace"],
    ),
]


def _configure_utf8_stdio() -> None:
    """Force UTF-8 encoding on stdio streams when supported."""
    for stream in (sys.stdin, sys.stdout):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            reconf(encoding="utf-8", errors="replace")


def _load_memory_engine() -> Any:
    """Lazy-import memory_engine from the sibling memory-sync skill scripts dir."""
    engine_dir_str = str(ENGINE_DIR)
    if engine_dir_str not in sys.path:
        sys.path.insert(0, engine_dir_str)
    try:
        return importlib.import_module("memory_engine")
    except Exception as exc:
        raise RuntimeError(
            f"memory_engine module unavailable in {ENGINE_DIR}: {exc}"
        ) from exc


def _format_rows(engine: Any, rows: list[dict], fmt: str) -> Any:
    return engine.memory_insights.to_toon(rows) if fmt == "toon" else rows


def _call_tool(name: str, args: dict[str, Any]) -> Any:
    """Dispatch an MCP tool call to memory_engine functions."""
    workspace = str(args.get("workspace") or os.getcwd())
    engine = _load_memory_engine()
    fmt = str(args.get("format") or "json").lower()

    if name == "memory_hydrate":
        try:
            brief = engine.hydrate_brief(workspace)
        except FileNotFoundError:
            brief = None
        return brief if brief else HYDRATE_EMPTY_MSG

    if name == "symbol_lookup":
        query = str(args.get("query") or "")
        if not query:
            raise ValueError("query is required for symbol_lookup")
        limit = int(args.get("limit") or 10)
        return _format_rows(engine, engine.lookup_symbol(workspace, query, limit=limit), fmt)

    if name == "memory_search":
        query = str(args.get("query") or "")
        if not query:
            raise ValueError("query is required for memory_search")
        limit = int(args.get("limit") or 8)
        return _format_rows(engine, engine.search_memory(workspace, query, limit=limit), fmt)

    if name == "memory_checkpoint":
        engine.init_memory(workspace)
        vt_raw = args.get("verified_tests")
        vt_str = ", ".join(str(x) for x in vt_raw) if isinstance(vt_raw, list) else str(vt_raw or "")
        return engine.checkpoint_state(
            workspace,
            active_task=str(args.get("active_task") or ""),
            status=str(args.get("status") or ""),
            verified_tests=vt_str,
            blockers=args.get("blockers"),
            next_steps=args.get("next_steps"),
            note_shard=str(args.get("note_shard") or ""),
            note_title=str(args.get("note_title") or ""),
            note_body=str(args.get("note_body") or ""),
        )

    if name == "memory_reindex":
        engine.init_memory(workspace)
        return engine.index_workspace(workspace, paths=args.get("paths"))

    if name == "memory_lesson":
        action = str(args.get("action") or "list").lower()
        if action == "record":
            return engine.record_lesson(
                workspace,
                outcome=str(args.get("outcome") or ""),
                query=str(args.get("query") or ""),
                paths=args.get("paths"),
                correction=str(args.get("correction") or ""),
            )
        rows = engine.list_lessons(
            workspace,
            query=str(args.get("query") or ""),
            outcome=str(args.get("outcome") or ""),
            limit=int(args.get("limit") or 10),
        )
        return _format_rows(engine, rows, fmt)

    if name == "context_budget":
        cockpit_dir = PLUGIN_ROOT / "skills" / "context-guard" / "scripts"
        if str(cockpit_dir) not in sys.path:
            sys.path.insert(0, str(cockpit_dir))
        import context_cockpit
        rep = context_cockpit.analyze_conversation_context(
            conv_id=args.get("conversation_id"),
            max_tokens=int(args.get("max_tokens") or 200000),
            workspace=Path(workspace) if workspace else None,
        )
        if args.get("generate_html"):
            html_path = (Path(workspace) if workspace else Path.cwd()) / "CONTEXT_COCKPIT.html"
            context_cockpit.generate_html_cockpit(rep, html_path)
            rep["html_path"] = str(html_path)
        return rep

    raise ValueError(f"Unknown tool: {name}")


def _handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    """Process one JSON-RPC 2.0 request object; return None for notifications."""
    has_id = "id" in req
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params")
    if not isinstance(params, dict):
        params = {}

    if not isinstance(method, str) or not method:
        if not has_id:
            return None
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32600, "message": "Invalid Request"},
        }

    if method == "notifications/initialized" or (not has_id and method.startswith("notifications/")):
        return None

    if not has_id:
        return None

    if method == "initialize":
        client_ver = params.get("protocolVersion")
        proto = client_ver if isinstance(client_ver, str) and client_ver in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": proto,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments")
        if not isinstance(tool_args, dict):
            tool_args = {}
        try:
            if not isinstance(tool_name, str) or not tool_name:
                raise ValueError("Missing tool name")
            result = _call_tool(tool_name, tool_args)
            text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            payload = {"content": [{"type": "text", "text": text}], "isError": False}
        except Exception as exc:
            payload = {
                "content": [{"type": "text", "text": json.dumps({"error": str(exc)}, ensure_ascii=False)}],
                "isError": True,
            }
        return {"jsonrpc": "2.0", "id": req_id, "result": payload}

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _emit(resp: dict[str, Any]) -> None:
    """Write a single newline-delimited JSON-RPC response and flush."""
    sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    """Run the stdio MCP JSON-RPC 2.0 event loop until EOF."""
    _configure_utf8_stdio()
    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        raw = line.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except Exception:
            _emit({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        if not isinstance(req, dict):
            _emit({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}})
            continue
        resp = _handle_request(req)
        if resp is not None:
            _emit(resp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
