"""gurdy CLI entry point.

Subcommands mirror the LLM-facing tool surface:

    gurdy describe <topic> --pair <id>
    gurdy compile <spec.json> [--source <path>] [-o <out.json>]
    gurdy dispatch <artifact.json> <directive.json>
    gurdy lift <artifact.json> <raw.json>
    gurdy introspect <artifact.json> [--layer L] [--nid N] [--role R]
    gurdy simulate <spec.json> <binding.json> --max-steps N
    gurdy evaluate <artifact.json> <binding.json> --max-steps N
    gurdy cross-check <spec.json> <src-binding.json> <reas-binding.json> --max-steps N
    gurdy replay <artifact.json> <raw.json>
    gurdy check <spec.json> <binding.json> --max-steps N
    gurdy pairs

Specs and artifacts are exchanged through small JSON files. The
framework writes only structural fields here; pair-specific fields
are pickled inside under ``payload``. The CLI's primary purpose is to
make the tool surface usable from a shell without writing Python.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

from gurdy.core.annotation.lookup import IntrospectQuery
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.pair import CompiledArtifact, list_pairs


def _load_pair_module(name: str) -> None:
    """Best-effort import of a pair module by identifier."""
    candidates = [name.replace("-", "_"), name]
    for n in candidates:
        try:
            importlib.import_module(f"gurdy.pairs.{n}")
            return
        except ImportError:
            continue


def _load_pair_modules_for_known_ids(args: argparse.Namespace) -> None:
    """Try to import pair packages so they can self-register."""
    pair_id = getattr(args, "pair", None)
    if pair_id:
        _load_pair_module(pair_id)


def _load_all_translation_modules() -> None:
    """Best-effort import of every pair and hop package so they self-register
    (their hops, pairs, and language descriptors) before a graph query."""
    import pkgutil

    for pkgname in ("gurdy.pairs", "gurdy.hops"):
        try:
            pkg = importlib.import_module(pkgname)
        except ImportError:
            continue
        for mod in pkgutil.iter_modules(pkg.__path__):
            try:
                importlib.import_module(f"{pkgname}.{mod.name}")
            except ImportError:
                continue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gurdy",
        description=(
            "hurdy-gurdy: deterministic translations from source languages "
            "to reasoning languages, for use by external solvers and LLMs."
        ),
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_desc = sub.add_parser("describe", help="show a schema entry")
    p_desc.add_argument("topic")
    p_desc.add_argument("--pair", required=True)

    p_comp = sub.add_parser("compile", help="compile a spec to a layered artifact")
    p_comp.add_argument("spec", help="path to a JSON spec file")
    p_comp.add_argument("--source", help="optional source path", default=None)
    p_comp.add_argument("-o", "--output", default=None)

    p_disp = sub.add_parser("dispatch", help="run a single solver")
    p_disp.add_argument("artifact", help="path to a compiled-artifact JSON")
    p_disp.add_argument("directive", help="path to a directive JSON")

    p_lift = sub.add_parser("lift", help="lift a raw solver result")
    p_lift.add_argument("artifact")
    p_lift.add_argument("raw")

    p_intro = sub.add_parser("introspect", help="query the annotation")
    p_intro.add_argument("artifact")
    p_intro.add_argument("--layer", default=None)
    p_intro.add_argument("--nid", type=int, default=None)
    p_intro.add_argument("--role", default=None)

    p_sim = sub.add_parser("simulate", help="run the source interpreter")
    p_sim.add_argument("spec")
    p_sim.add_argument("binding")
    p_sim.add_argument("--max-steps", type=int, default=64)
    p_sim.add_argument("--source", default=None)

    p_eval = sub.add_parser("evaluate", help="run the reasoning interpreter")
    p_eval.add_argument("artifact")
    p_eval.add_argument("binding")
    p_eval.add_argument("--max-steps", type=int, default=64)

    p_xc = sub.add_parser("cross-check", help="align source and reasoning interpreters")
    p_xc.add_argument("spec")
    p_xc.add_argument("source_binding", help="JSON for the source-side binding")
    p_xc.add_argument("reasoning_binding", help="JSON for the reasoning-side binding")
    p_xc.add_argument("--max-steps", type=int, default=64)
    p_xc.add_argument("--source", default=None)

    p_rep = sub.add_parser("replay", help="replay a solver witness through both interpreters")
    p_rep.add_argument("artifact")
    p_rep.add_argument("raw")

    p_chk = sub.add_parser("check", help="evaluate spec predicates on a concrete trace")
    p_chk.add_argument("spec")
    p_chk.add_argument("binding")
    p_chk.add_argument("--max-steps", type=int, default=64)
    p_chk.add_argument("--source", default=None)

    sub.add_parser("pairs", help="list registered pairs")

    sub.add_parser("languages", help="list registered languages")

    p_routes = sub.add_parser(
        "routes", help="enumerate translation routes between two languages"
    )
    p_routes.add_argument("in_lang", help="source (input) language id")
    p_routes.add_argument("out_lang", help="target language id")

    return parser


# ---------------------------------------------------------------------------
# Helpers (artifact and spec serialization)
# ---------------------------------------------------------------------------


def _read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | None, payload: Any) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, default=_jsonify_default)
    if path is None:
        print(text)
    else:
        Path(path).write_text(text, encoding="utf-8")


def _jsonify_default(o: Any) -> Any:
    if isinstance(o, bytes):
        return {"__bytes_hex__": o.hex()}
    if hasattr(o, "to_jsonable"):
        return o.to_jsonable()
    if hasattr(o, "__dict__"):
        return o.__dict__
    return repr(o)


def _spec_from_json(obj: dict[str, Any]):
    """Reload a spec JSON produced by the pair's spec serializer.

    The pair is expected to provide ``Spec.from_jsonable``; the
    framework calls into it after routing on the ``pair`` field.
    """
    pair_id = obj.get("pair")
    if pair_id is None:
        raise ValueError("spec JSON missing 'pair' field")
    _load_pair_module(pair_id)
    from gurdy.core.pair import get_pair

    pair = get_pair(pair_id)
    spec_cls = pair.spec_class
    if not hasattr(spec_cls, "from_jsonable"):
        raise ValueError(
            f"spec class for pair {pair_id!r} does not implement from_jsonable"
        )
    return spec_cls.from_jsonable(obj)


def _artifact_from_json(obj: dict[str, Any]) -> CompiledArtifact:
    from gurdy.core.annotation.sidecar import AnnotationSidecar
    from gurdy.core.pair import Layer

    layers = {
        name: Layer(name=name, body=bytes.fromhex(L["body_hex"]), content_hash=L["hash"])
        for name, L in obj["layers"].items()
    }
    sidecar = AnnotationSidecar.from_json(json.dumps(obj["annotation"]))
    return CompiledArtifact(
        pair=obj["pair"],
        layers=layers,
        annotation=sidecar,
        flattened=bytes.fromhex(obj["flattened_hex"]),
        schema_version=obj["schema_version"],
        spec_hash=obj["spec_hash"],
    )


def _artifact_to_jsonable(art: CompiledArtifact) -> dict[str, Any]:
    return {
        "pair": art.pair,
        "schema_version": art.schema_version,
        "spec_hash": art.spec_hash,
        "layers": {
            name: {"body_hex": L.body.hex(), "hash": L.content_hash}
            for name, L in art.layers.items()
        },
        "annotation": json.loads(art.annotation.to_json()),
        "flattened_hex": art.flattened.hex(),
    }


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_describe(args) -> int:
    from gurdy.core.tools.describe import describe

    _load_pair_module(args.pair)
    entry = describe(args.topic, args.pair)
    if entry is None:
        print(f"no entry for {args.topic!r} in pair {args.pair!r}", file=sys.stderr)
        return 1
    print(f"# {entry.heading}\n")
    if entry.body:
        print(entry.body)
    if entry.subheadings:
        print("\nSubsections:")
        for sh in entry.subheadings:
            print(f"  - {sh}")
    if entry.hint:
        print(f"\n[hint] {entry.hint}")
    meta = []
    if entry.schema_version:
        meta.append(f"schema_version={entry.schema_version}")
    if entry.interpreter_version:
        meta.append(f"interpreter_version={entry.interpreter_version}")
    if meta:
        print(f"\n[pair] {' '.join(meta)}")
    return 0


def _cmd_compile(args) -> int:
    from gurdy.core.tools.compile import compile_spec

    spec = _spec_from_json(_read_json(args.spec))
    payload = Path(args.source) if args.source else None
    artifact = compile_spec(spec, payload)
    _write_json(args.output, _artifact_to_jsonable(artifact))
    return 0


def _cmd_dispatch(args) -> int:
    from gurdy.core.tools.dispatch import dispatch

    artifact = _artifact_from_json(_read_json(args.artifact))
    _load_pair_module(artifact.pair)
    directive_obj = _read_json(args.directive)
    directive = _SimpleDirective(**directive_obj)
    raw = dispatch(artifact, directive)
    _write_json(None, _raw_to_jsonable(raw))
    return 0


def _cmd_lift(args) -> int:
    from gurdy.core.tools.lift import lift

    artifact = _artifact_from_json(_read_json(args.artifact))
    _load_pair_module(artifact.pair)
    raw_obj = _read_json(args.raw)
    raw = RawSolverResult(
        verdict=raw_obj.get("verdict", "unknown"),
        elapsed=float(raw_obj.get("elapsed", 0.0)),
        engine=raw_obj.get("engine", ""),
        payload=raw_obj.get("payload"),
        reason=raw_obj.get("reason"),
    )
    out = lift(artifact, raw)
    _write_json(None, out)
    return 0


def _cmd_introspect(args) -> int:
    from gurdy.core.tools.introspect import introspect

    artifact = _artifact_from_json(_read_json(args.artifact))
    _load_pair_module(artifact.pair)
    q = IntrospectQuery(layer=args.layer, nid=args.nid, role=args.role)
    res = introspect(artifact, q)
    _write_json(None, [a.to_jsonable() for a in res.matches])
    return 0


def _binding_from_json(obj: dict[str, Any], *, kind: str):
    """Decode a binding JSON via the pair's binding class.

    ``kind`` is either ``"source"`` or ``"reasoning"``; the framework
    routes to the pair's ``RiscvInputBinding`` / ``Btor2ReasoningBinding``
    (and analogues for other pairs) via the ``__type__`` field.
    """
    pair_id = obj.get("pair")
    if pair_id is None:
        raise ValueError("binding JSON missing 'pair' field")
    _load_pair_module(pair_id)
    # Pair-specific binding classes register themselves; for now we
    # know the riscv-btor2 ones live at well-known import paths.
    type_name = obj.get("__type__", "")
    if pair_id == "riscv-btor2":
        if kind == "source" or type_name == "RiscvInputBinding":
            from gurdy.pairs.riscv_btor2.source_interp.bindings import (
                RiscvInputBinding,
            )

            return RiscvInputBinding.from_jsonable(obj)
        if kind == "reasoning" or type_name == "Btor2ReasoningBinding":
            from gurdy.pairs.riscv_btor2.reasoning_interp.bindings import (
                Btor2ReasoningBinding,
            )

            return Btor2ReasoningBinding.from_jsonable(obj)
    raise ValueError(
        f"don't know how to decode binding type {type_name!r} for pair {pair_id!r}"
    )


def _cmd_simulate(args) -> int:
    from gurdy.core.tools.simulate import simulate

    spec = _spec_from_json(_read_json(args.spec))
    binding = _binding_from_json(_read_json(args.binding), kind="source")
    payload = Path(args.source) if args.source else None
    trace = simulate(spec, binding, args.max_steps, source_payload=payload)
    _write_json(None, trace.to_jsonable())
    return 0


def _cmd_evaluate(args) -> int:
    from gurdy.core.tools.evaluate import evaluate

    artifact = _artifact_from_json(_read_json(args.artifact))
    _load_pair_module(artifact.pair)
    binding = _binding_from_json(_read_json(args.binding), kind="reasoning")
    trace = evaluate(artifact, binding, args.max_steps)
    _write_json(None, trace.to_jsonable())
    return 0


def _cmd_cross_check(args) -> int:
    from gurdy.core.tools.cross_check import cross_check

    spec = _spec_from_json(_read_json(args.spec))
    src_binding = _binding_from_json(_read_json(args.source_binding), kind="source")
    reas_binding = _binding_from_json(
        _read_json(args.reasoning_binding), kind="reasoning"
    )
    payload = Path(args.source) if args.source else None
    report = cross_check(
        spec, src_binding, reas_binding, args.max_steps, source_payload=payload
    )
    _write_json(None, report.to_jsonable())
    return 0


def _cmd_replay(args) -> int:
    from gurdy.core.tools.replay import replay

    artifact = _artifact_from_json(_read_json(args.artifact))
    _load_pair_module(artifact.pair)
    raw_obj = _read_json(args.raw)
    raw = RawSolverResult(
        verdict=raw_obj.get("verdict", "unknown"),
        elapsed=float(raw_obj.get("elapsed", 0.0)),
        engine=raw_obj.get("engine", ""),
        payload=raw_obj.get("payload"),
        reason=raw_obj.get("reason"),
    )
    joined = replay(artifact, raw)
    _write_json(None, joined.to_jsonable())
    return 0


def _cmd_check(args) -> int:
    from gurdy.core.tools.check import check

    spec = _spec_from_json(_read_json(args.spec))
    binding = _binding_from_json(_read_json(args.binding), kind="source")
    payload = Path(args.source) if args.source else None
    se = check(spec, binding, args.max_steps, source_payload=payload)
    _write_json(None, se.to_jsonable())
    return 0


def _cmd_pairs(args) -> int:
    pairs = list_pairs()
    if not pairs:
        print("(no pairs registered in this Python session)", file=sys.stderr)
        return 0
    for p in pairs:
        print(p)
    return 0


def _cmd_languages(args) -> int:
    from gurdy.core.language import get_language, list_languages

    _load_all_translation_modules()
    ids = list_languages()
    if not ids:
        print("(no languages registered in this Python session)", file=sys.stderr)
        return 0
    for i in ids:
        lang = get_language(i)
        extra = f"  [{', '.join(lang.reasons_via)}]" if lang.reasons_via else ""
        print(f"{lang.id}\t{lang.kind}\t{lang.semantics}{extra}")
    return 0


def _cmd_routes(args) -> int:
    from gurdy.core.route import routes

    _load_all_translation_modules()
    rs = routes(args.in_lang, args.out_lang)
    if not rs:
        print(
            f"(no route from {args.in_lang!r} to {args.out_lang!r})",
            file=sys.stderr,
        )
        return 0
    for r in rs:
        chain = " -> ".join(r.languages)
        hops = " | ".join(f"{h}:{t.value}" for h, t in zip(r.hops, r.tiers))
        det = "yes" if r.is_deterministic else "no"
        print(f"{chain}\ttrust={r.trust.value}\tdet={det}\t[{hops}]")
    return 0


def _raw_to_jsonable(raw: RawSolverResult) -> dict[str, Any]:
    payload: Any = raw.payload
    if isinstance(payload, (bytes, bytearray)):
        payload = {"__bytes_hex__": bytes(payload).hex()}
    return {
        "verdict": raw.verdict,
        "elapsed": raw.elapsed,
        "engine": raw.engine,
        "payload": payload,
        "reason": raw.reason,
    }


class _SimpleDirective:
    def __init__(self, **kwargs: Any):
        self.engine = kwargs.get("engine")
        self.bound = kwargs.get("bound")
        self.timeout = kwargs.get("timeout")
        self.havoc_registers = frozenset(kwargs.get("havoc_registers", []))
        self.extra_options = dict(kwargs.get("extra_options", {}))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


HANDLERS = {
    "describe": _cmd_describe,
    "compile": _cmd_compile,
    "dispatch": _cmd_dispatch,
    "lift": _cmd_lift,
    "introspect": _cmd_introspect,
    "simulate": _cmd_simulate,
    "evaluate": _cmd_evaluate,
    "cross-check": _cmd_cross_check,
    "replay": _cmd_replay,
    "check": _cmd_check,
    "pairs": _cmd_pairs,
    "languages": _cmd_languages,
    "routes": _cmd_routes,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from gurdy import __version__

        print(__version__)
        return 0
    if args.command is None:
        parser.print_help()
        return 0
    handler = HANDLERS[args.command]
    return handler(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
