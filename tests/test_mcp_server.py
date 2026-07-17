"""The MCP server (gurdy/mcp.py): the player surface over stdio
JSON-RPC, scoped to the use plane plus demand recording
(ARCHITECTURE.md §0). Exercised end to end through a real subprocess:
initialize/list/call round-trips, the demand a failed why_not records
through the served surface, tool errors in-result, protocol errors as
JSON-RPC errors — and the exposure rule pinned: the tool list contains
no write to the evolution plane."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _session(messages, env=None):
    """Feed newline-delimited JSON-RPC messages; return replies by id."""
    proc = subprocess.run(
        [sys.executable, "-m", "gurdy", "mcp"],
        input="\n".join(json.dumps(m) for m in messages) + "\n",
        capture_output=True, text=True, cwd=_REPO,
        env={**os.environ, **(env or {})}, timeout=300)
    assert proc.returncode == 0, proc.stderr
    replies = {}
    for line in proc.stdout.splitlines():
        if line.strip():
            m = json.loads(line)
            replies[m.get("id")] = m
    return replies


def _tool_result(reply):
    assert not reply["result"]["isError"], reply
    return json.loads(reply["result"]["content"][0]["text"])


_INIT = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
         "params": {"protocolVersion": "2025-03-26"}}
_READY = {"jsonrpc": "2.0", "method": "notifications/initialized"}


def _call(mid, name, args=None):
    return {"jsonrpc": "2.0", "id": mid, "method": "tools/call",
            "params": {"name": name, "arguments": args or {}}}


class TestMcpServer(unittest.TestCase):
    def test_initialize_list_and_discovery_calls(self):
        replies = _session([
            _INIT, _READY,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            _call(2, "languages"),
            _call(3, "routes", {"source": "riscv", "target": "smtlib",
                                "observables": ["pc"],
                                "shape": "reachability"}),
        ])
        init = replies[0]["result"]
        self.assertEqual(init["serverInfo"]["name"], "hurdy-gurdy")
        self.assertEqual(init["protocolVersion"], "2025-03-26")
        names = {t["name"] for t in replies[1]["result"]["tools"]}
        langs = _tool_result(replies[2])
        self.assertIn("btor2", langs)
        self.assertIn("reachability", langs["btor2"]["question_shapes"])
        report = _tool_result(replies[3])
        self.assertEqual(len(report), 2)
        for e in report:
            self.assertTrue(e["feasibility"]["feasible"])
        # the notification produced no reply
        self.assertNotIn(None, replies)
        # ... and the exposure rule: use plane + demand recording only —
        # nothing registers, ratchets, or writes a protected field.
        self.assertEqual(names, {
            "languages", "pairs", "routes", "coverage", "route_coverage",
            "why_not", "trust_options", "recommendations",
            "suggest_reduction", "reach"})

    def test_why_not_records_demand_through_the_served_surface(self):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        try:
            replies = _session(
                [_INIT, _READY,
                 _call(1, "why_not", {"source": "riscv",
                                      "observables": ["pc"],
                                      "shape": "liveness",
                                      "origin": "campaign"})],
                env={"GURDY_LEDGER": path})
            rec = _tool_result(replies[1])
            self.assertFalse(rec["answerable"])
            self.assertEqual(rec["obstacle"], "shape")
            with open(path, encoding="utf-8") as f:
                demands = [json.loads(l) for l in f if l.strip()]
            self.assertEqual(len(demands), 1)
            self.assertEqual(demands[0]["kind"], "demand")
            self.assertEqual(demands[0]["origin"], "campaign")
        finally:
            os.unlink(path)

    def test_tool_error_in_result_and_protocol_error_as_jsonrpc(self):
        replies = _session([
            _INIT, _READY,
            _call(1, "coverage", {"pair": "no-such-pair"}),
            {"jsonrpc": "2.0", "id": 2, "method": "bogus/method"},
        ])
        self.assertTrue(replies[1]["result"]["isError"])
        self.assertEqual(replies[2]["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
