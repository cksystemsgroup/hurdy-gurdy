"""Smoke test for bench/riscv-btor2/mcp_server.py.

Drives the JSON-RPC stdio server through the four methods that
matter -- initialize, tools/list, tools/call, and an unknown
method -- and asserts each returns a well-shaped envelope. Calls
``introspect`` (a B-mode tool that doesn't need a built ELF) so the
test runs without the RV64 toolchain.

The MCP server is the load-bearing piece for conditions B and C
under the claude-code adapter: claude spawns it as an MCP stdio
child, and a regression here would silently break every B/C cell.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
SERVER = REPO / "bench" / "riscv-btor2" / "mcp_server.py"
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"


def _drive(messages: list[dict], mode: str = "B", timeout: int = 30) -> list[dict]:
    """Send a sequence of JSON-RPC messages to the server, return
    the parsed responses (skipping notification echoes)."""
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    proc = subprocess.run(
        [sys.executable, str(SERVER), "--mode", mode],
        input=payload,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, (
        f"server exited {proc.returncode}\nstderr:\n{proc.stderr}"
    )
    out: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


@pytest.mark.skipif(not SERVER.exists(), reason="mcp_server script missing")
def test_initialize_and_tools_list_mode_b():
    responses = _drive([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ])
    # Notification gets no response, so we expect 2 entries.
    assert len(responses) == 2

    init_rep = responses[0]
    assert init_rep["id"] == 1
    assert "result" in init_rep
    assert init_rep["result"]["protocolVersion"]
    assert init_rep["result"]["serverInfo"]["name"] == "hurdy-gurdy-bench"

    list_rep = responses[1]
    assert list_rep["id"] == 2
    names = {t["name"] for t in list_rep["result"]["tools"]}
    assert names == {"compile", "dispatch", "lift", "introspect"}
    # MCP uses inputSchema (camelCase), not Anthropic's input_schema.
    for tool in list_rep["result"]["tools"]:
        assert "inputSchema" in tool
        assert "input_schema" not in tool


@pytest.mark.skipif(not SERVER.exists(), reason="mcp_server script missing")
def test_tools_list_mode_c():
    responses = _drive([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ], mode="C")
    list_rep = responses[1]
    names = {t["name"] for t in list_rep["result"]["tools"]}
    assert names == {"solve"}


@pytest.mark.skipif(not SERVER.exists(), reason="mcp_server script missing")
@pytest.mark.skipif(
    not (CORPUS / "0007-simple-add-baseline" / "source.elf").exists(),
    reason="corpus binary not built",
)
def test_tools_call_introspect():
    spec = {
        "pair": "riscv-btor2",
        "fields": {
            "binary": {"path": str(
                (CORPUS / "0007-simple-add-baseline" / "source.elf").resolve()
            )},
            "scope": {"entry_function": "_start", "included_callees": []},
            "entry": {"excluded_pc_ranges": []},
            "observables": [],
            "assumptions": [],
            "learned": [],
            "property": {"expression": "const(true)", "negate": False},
            "analysis": {
                "engine": "z3-bmc", "bound": 4, "timeout": 30,
                "havoc_registers": ["__set__"], "extra_options": {},
            },
        },
    }
    responses = _drive([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "introspect", "arguments": {"spec": spec}}},
    ])
    call_rep = responses[1]
    assert call_rep["id"] == 2
    assert "result" in call_rep
    content = call_rep["result"]["content"]
    assert content[0]["type"] == "text"
    body = json.loads(content[0]["text"])
    # Well-formed spec → no diagnostics.
    assert body == {"diagnostics": []}


@pytest.mark.skipif(not SERVER.exists(), reason="mcp_server script missing")
def test_unknown_method_returns_jsonrpc_error():
    responses = _drive([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "does/not/exist", "params": {}},
    ])
    err_rep = responses[1]
    assert "error" in err_rep
    assert err_rep["error"]["code"] == -32601


@pytest.mark.skipif(not SERVER.exists(), reason="mcp_server script missing")
def test_unknown_tool_returns_jsonrpc_error():
    responses = _drive([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "no_such_tool", "arguments": {}}},
    ])
    err_rep = responses[1]
    assert "error" in err_rep
    assert err_rep["error"]["code"] == -32602
