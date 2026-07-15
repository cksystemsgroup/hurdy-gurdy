"""The MCP server — the player surface served over the Model Context
Protocol (INTERFACE.md §1; ARCHITECTURE.md §0).

The MCP surface is the **use plane plus demand recording**, exactly as
ARCHITECTURE.md §0 rules: every tool reads the registry and the books
and produces evidence-carrying results; the one permitted write is the
demand a failed ``why_not`` records (origin-tagged, append-only
observability). No tool registers a pair, touches a protected field, or
reaches the ratchet — the graph never grows through a session.

Zero dependencies by design: the stdio transport is newline-delimited
JSON-RPC 2.0, and this module implements the subset MCP clients need —
``initialize``, ``notifications/initialized``, ``ping``, ``tools/list``,
``tools/call``. Tool results are returned as JSON text content;
tool-level failures are reported in-result (``isError``), protocol-level
failures as JSON-RPC errors. stdout carries protocol only; diagnostics
go to stderr. Run: ``gurdy mcp`` (or ``python -m gurdy mcp``).
"""

from __future__ import annotations

import json
import sys
from typing import Any

# The import is the registration: reuse the CLI's full-board imports.
from . import cli as _cli  # noqa: F401
from . import __version__
from .core import grade, ledger, registry, route, trust, whynot

PROTOCOL_VERSIONS = ("2025-03-26", "2024-11-05")


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props,
            "required": required or []}


_STR = {"type": "string"}
_INT = {"type": "integer"}
_STRLIST = {"type": "array", "items": {"type": "string"}}

TOOLS: list[dict[str, Any]] = [
    {"name": "languages",
     "description": "Registered languages: id, interpreter roles, status, "
                    "declared question shapes (reasoning languages).",
     "inputSchema": _obj({})},
    {"name": "pairs",
     "description": "Registered pairs: source→target, declared fidelity, "
                    "direction, status, semantic artifact.",
     "inputSchema": _obj({})},
    {"name": "routes",
     "description": "Enumerate routes between two languages, annotated on "
                    "the four axes (fidelity/assurance, direction, "
                    "feasibility, measured cost) with Pareto-dominance "
                    "marks. Enumerates and annotates; never chooses.",
     "inputSchema": _obj({"source": _STR, "target": _STR,
                          "observables": _STRLIST, "shape": _STR},
                         ["source", "target"])},
    {"name": "coverage",
     "description": "A pair's construct coverage against its inventory.",
     "inputSchema": _obj({"pair": _STR}, ["pair"])},
    {"name": "route_coverage",
     "description": "Composed construct coverage of every route between "
                    "two languages (conjoined with per-hop squares).",
     "inputSchema": _obj({"source": _STR, "target": _STR, "k": _INT},
                         ["source", "target"])},
    {"name": "why_not",
     "description": "The answerability diagnosis: walks the five obstacles "
                    "(connectivity, loss, shape, cost, trust) and returns "
                    "the first failure as a demand record naming the "
                    "generation target — recorded in the books when a "
                    "ledger is configured. Registration stays a human act.",
     "inputSchema": _obj({"source": _STR, "observables": _STRLIST,
                          "shape": _STR, "verdict": _STR, "floor": _STR,
                          "origin": {"type": "string",
                                     "enum": ["organic", "campaign"]}},
                         ["source"])},
    {"name": "trust_options",
     "description": "The trust view for source→target: per-route assurance, "
                    "branch independence over declared semantic artifacts, "
                    "the anchor census, and the honest option set when a "
                    "floor is unmet. Read-only.",
     "inputSchema": _obj({"source": _STR, "target": _STR, "floor": _STR},
                         ["source", "target"])},
    {"name": "recommendations",
     "description": "The books' demand side aggregated per generation "
                    "target: distinct questions, obstacles, origins. "
                    "Evidence volume, not a verdict — a human decides.",
     "inputSchema": _obj({})},
    {"name": "suggest_reduction",
     "description": "The BTOR2 abstraction advisor: cone of influence, the "
                    "zero-precision-loss free havoc set, the "
                    "farthest-first refinement ladder, observed interval "
                    "seeds. Advisory parameters only.",
     "inputSchema": _obj({"system": _STR, "k": _INT, "samples": _INT},
                         ["system"])},
    {"name": "reach",
     "description": "Decide bounded reachability for a BTOR2 system via "
                    "the SMT bridge (the one nondeterministic tool); on "
                    "reachable, the model is replayed through the shared "
                    "interpreter (witness_ok) — the evidence, not the "
                    "solver's say-so.",
     "inputSchema": _obj({"system": _STR, "k": _INT}, ["system", "k"])},
]


def _call(name: str, args: dict[str, Any]) -> Any:
    if name == "languages":
        return {lid: {"roles": [r for r, f in
                                (("source", lang.source_interpreter),
                                 ("target", lang.target_interpreter)) if f],
                      "status": lang.status.value,
                      "question_shapes": list(lang.question_shapes)}
                for lid, lang in sorted(registry.list_languages().items())}
    if name == "pairs":
        return {pid: {"source": p.source, "target": p.target,
                      "fidelity": p.fidelity, "direction": p.direction,
                      "status": p.status.value,
                      "semantic_artifact": p.semantic_artifact}
                for pid, p in sorted(registry.list_pairs().items())}
    if name == "routes":
        return route.route_report(args["source"], args["target"],
                                  observables=args.get("observables"),
                                  shape=args.get("shape"))
    if name == "coverage":
        pair = registry.get_pair(args["pair"])
        if not pair.probes:
            return {"error": f"{args['pair']}: no coverage inventory"}
        from .core.coverage import measure
        rep = measure(pair.translator, pair.probes)
        return {"covered": len(rep.covered), "total": rep.total,
                "missing": dict(sorted(rep.missing.items()))}
    if name == "route_coverage":
        reports = grade.composed_coverage_by_route(
            args["source"], args["target"], k=int(args.get("k", 1)))
        return {" -> ".join(r): {"covered": len(rep.covered),
                                 "total": rep.total,
                                 "missing": dict(sorted(rep.missing.items()))}
                for r, rep in reports.items()}
    if name == "why_not":
        return whynot.why_not(args["source"], args.get("observables"),
                              args.get("shape"),
                              verdict=args.get("verdict"),
                              floor=args.get("floor"),
                              origin=args.get("origin", "organic"))
    if name == "trust_options":
        return trust.trust_options(args["source"], args["target"],
                                   floor=args.get("floor"))
    if name == "recommendations":
        return ledger.demand_summary()
    if name == "suggest_reduction":
        from .languages.btor2.coi import suggest_reduction
        return suggest_reduction(args["system"], k=int(args.get("k", 8)),
                                 samples=int(args.get("samples", 4)))
    if name == "reach":
        from .pairs.btor2_smtlib import reach
        info = reach(args["system"], int(args["k"]))
        out = {"verdict": info["verdict"].value}
        for key in ("witness_ok", "smt_model_ok", "behavior"):
            if key in info:
                out[key] = info[key]
        return out
    raise ValueError(f"unknown tool: {name}")


def _handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        client = (msg.get("params") or {}).get("protocolVersion")
        version = client if client in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "hurdy-gurdy", "version": __version__},
            "instructions": (
                "The hurdy-gurdy player surface: the use plane plus demand "
                "recording (ARCHITECTURE.md §0). Tools enumerate, annotate, "
                "and account; none chooses, none registers — answers never "
                "write; growth never answers."),
        }}
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = _call(name, args)
            text = json.dumps(result, indent=2, sort_keys=True, default=str)
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": text}],
                "isError": False}}
        except Exception as exc:  # tool failure -> in-result error (MCP)
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text",
                             "text": f"{type(exc).__name__}: {exc}"}],
                "isError": True}}
    if mid is None:
        return None  # unknown notification: ignore
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None) -> int:
    """Serve until EOF. One JSON-RPC message per line in, one per line
    out; notifications produce no output."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            print(json.dumps({"jsonrpc": "2.0", "id": None,
                              "error": {"code": -32700,
                                        "message": "parse error"}}),
                  file=stdout, flush=True)
            continue
        reply = _handle(msg)
        if reply is not None:
            print(json.dumps(reply), file=stdout, flush=True)
    return 0
