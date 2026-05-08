"""Stdio MCP server exposing the bench's condition B / C tool surface.

Implements the JSON-RPC 2.0 / MCP stdio protocol by hand (no SDK
dependency) so the spawned ``claude`` subprocess can call the same
B_TOOLS and tool_solve that the in-process vendor adapters use. The
server is a one-shot child: ``claude`` spawns it, it runs until
stdin closes (the parent exits), then dies. Caches in
``harness`` (artifact, raw-result, source) are therefore per-cell.

Two modes:

  --mode B
      Exposes ``compile``, ``dispatch``, ``lift``, ``introspect`` --
      the pair-aware translator-layer tools. Tool schemas are
      loaded from prompts/tools_b.json so the LLM and the bench
      see byte-identical declarations.

  --mode C
      Exposes ``solve`` (raw solver, no translation help). Schema
      from prompts/tools_c.json.

Wire format: line-delimited JSON-RPC 2.0 on stdin/stdout; logs to
stderr. The minimum method set to make claude --mcp-config work is
``initialize``, ``notifications/initialized``, ``tools/list``,
``tools/call``. Anything else returns -32601 (method not found).

Run directly to smoke-test:

    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \\
        | python bench/riscv-btor2/mcp_server.py --mode B
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable


PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "hurdy-gurdy-bench"
SERVER_VERSION = "0.1"


def _log(msg: str) -> None:
    """Stderr-only log; stdout is reserved for JSON-RPC traffic."""
    print(f"[mcp_server] {msg}", file=sys.stderr, flush=True)


def _load_tools(mode: str) -> tuple[list[dict], dict[str, Callable]]:
    """Return (tool_defs, tool_callables).

    Tool defs are MCP-shaped: {name, description, inputSchema}.
    Anthropic-format tool schemas (input_schema) get renamed to
    inputSchema; we share prompts/tools_*.json as the single source
    of truth.
    """
    bench_root = Path(__file__).resolve().parent
    repo_root = bench_root.parents[1]

    # Make `import harness` resolve and let harness's imports of
    # gurdy.* find the package without an install.
    sys.path.insert(0, str(bench_root))
    sys.path.insert(0, str(repo_root))
    import harness  # type: ignore

    if mode == "B":
        schema_path = bench_root / "prompts" / "tools_b.json"
        callables = dict(harness.B_TOOLS)
    elif mode == "C":
        schema_path = bench_root / "prompts" / "tools_c.json"
        callables = {"solve": harness.tool_solve}
    else:
        raise ValueError(f"unknown mode {mode!r}; expected 'B' or 'C'")

    raw = json.loads(schema_path.read_text())
    defs: list[dict] = []
    for entry in raw:
        defs.append({
            "name": entry["name"],
            "description": entry.get("description", ""),
            # Anthropic uses input_schema; MCP uses inputSchema.
            "inputSchema": entry.get("input_schema") or entry.get("inputSchema") or {},
        })
    # Cross-check: every callable has a schema, every schema has a
    # callable. Catches drift between prompts/tools_*.json and the
    # B_TOOLS / tool_solve mapping.
    declared = {d["name"] for d in defs}
    implemented = set(callables)
    if declared != implemented:
        raise RuntimeError(
            f"tool surface drift in mode {mode}: "
            f"declared-only={declared - implemented}, "
            f"implemented-only={implemented - declared}"
        )
    return defs, callables


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _error_response(req_id: Any, code: int, message: str, data: Any = None) -> dict:
    err: dict = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _ok_response(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


# Pedagogical hints attached to tool errors so weaker callers get
# directly actionable feedback instead of just a class+message. The
# 2026-05-08 Haiku × B regression had 8 consecutive compile failures
# of the form "ValueError: unexpected character '=' at position N"
# because Haiku used Python-style `==` rather than the spec DSL's
# `eq(a, b)`. The hint surfaces the documented operators inline.
_DSL_HINT = (
    "Property/constraint/assumption expressions use a small s-expression "
    "DSL, NOT Python or C syntax. There is no `==`, `!=`, `<`, `>`, `&&`, "
    "or `||`. Valid forms: pc | true | false | <int> | reg(N) | "
    "mem(addr,width) | const(v) | eq | neq | lt/le/gt/ge (signed) | "
    "ltu/leu/gtu/geu (unsigned) | and | or | xor | not | add | sub. "
    "Property objects have exactly two fields: {expression: <DSL string>, "
    "negate: bool}; there is no `affinity`, `reach`, `assertion`, or "
    "similar field. Worked example: "
    "{\"expression\": \"and(eq(pc, const(0x10008)), eq(reg(10), const(12)))\", "
    "\"negate\": false}."
)


def _hint_for(tool_name: str | None, exc: Exception) -> str | None:
    """Return a pedagogical hint string for a failed tool call, or
    None if no special guidance applies. Keeps the hints scoped:
    only tools that consume a spec get the DSL hint, and only when
    the exception class suggests a syntax / shape problem."""
    if tool_name in {"compile", "introspect"} and isinstance(
        exc, (ValueError, KeyError, TypeError)
    ):
        return _DSL_HINT
    return None


def _handle(
    req: dict,
    tool_defs: list[dict],
    tool_callables: dict[str, Callable],
) -> dict | None:
    """Dispatch one JSON-RPC message. Returns the response dict, or
    None for notifications (no response per JSON-RPC)."""
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}
    is_notification = "id" not in req

    if method == "initialize":
        return _ok_response(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    if method == "notifications/initialized":
        return None  # client handshake complete; no response

    if method == "tools/list":
        return _ok_response(req_id, {"tools": tool_defs})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        fn = tool_callables.get(name)
        if fn is None:
            return _error_response(
                req_id, -32602, f"tool {name!r} not registered"
            )
        try:
            result = fn(**arguments)
        except TypeError as exc:
            err: dict[str, Any] = {"error": "TypeError", "message": str(exc)}
            hint = _hint_for(name, exc)
            if hint:
                err["hint"] = hint
            return _ok_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(err)}],
                "isError": True,
            })
        except Exception as exc:
            _log(f"tool {name!r} raised: {exc}\n{traceback.format_exc()}")
            err = {"error": type(exc).__name__, "message": str(exc)}
            hint = _hint_for(name, exc)
            if hint:
                err["hint"] = hint
            return _ok_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(err)}],
                "isError": True,
            })
        return _ok_response(req_id, {
            "content": [{"type": "text", "text": json.dumps(result)}],
        })

    if method == "ping":
        return _ok_response(req_id, {})

    if is_notification:
        return None  # silently ignore unknown notifications

    return _error_response(req_id, -32601, f"method {method!r} not implemented")


def serve(mode: str) -> int:
    try:
        tool_defs, tool_callables = _load_tools(mode)
    except Exception as exc:
        _log(f"startup failed: {exc}\n{traceback.format_exc()}")
        return 2

    _log(f"ready: mode={mode} tools={[d['name'] for d in tool_defs]}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _send(_error_response(None, -32700, f"parse error: {exc}"))
            continue
        try:
            resp = _handle(req, tool_defs, tool_callables)
        except Exception as exc:
            _log(f"handler crashed: {exc}\n{traceback.format_exc()}")
            resp = _error_response(req.get("id"), -32603, "internal error", str(exc))
        if resp is not None:
            _send(resp)
    _log("stdin closed; exiting")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("B", "C"), required=True)
    args = p.parse_args(argv)
    return serve(args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
