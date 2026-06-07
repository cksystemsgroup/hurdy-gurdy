"""Alignment oracle for the wasm-btor2 pair (P5).

Runs WasmSourceInterpreter and Btor2ReasoningInterpreter on the same
concrete inputs and asserts that observable state (locals, trap flag)
agrees step-by-step.

P5 target: 0001-i32-add-wrap — a two-param i32.add function that
exercises the full PC-keyed ITE dispatch path of the translator.

Usage::

    python bench/wasm-btor2/oracle_align.py
    python bench/wasm-btor2/oracle_align.py --params 3 5 --bound 8
    python bench/wasm-btor2/oracle_align.py --verbose

Correctness contract (V2_BOOTSTRAP.md §1):
  For every concrete (spec, wasm_module, params) triple the source
  interpreter accepts, the BTOR2 reasoning interpreter driven from
  the same initial state must produce the same locals and trap flag
  at every step up to the source trace's length.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

# Allow running as a standalone script from any cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.core.btor2.parser import from_text as btor2_parse
from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter
from gurdy.pairs.wasm_btor2.source import load_wasm_source
from gurdy.pairs.wasm_btor2.source_interp.bindings import WasmInputBinding
from gurdy.pairs.wasm_btor2.source_interp.interpreter import WasmSourceInterpreter
from gurdy.pairs.wasm_btor2.spec import (
    AnalysisScope,
    PropertyKind,
    QuestionSpec,
    WasmBtor2Spec,
    WasmModuleRef,
)
from gurdy.pairs.wasm_btor2.translation import SCHEMA_VERSION, Translator

ORACLE_VERSION = "1.0.0"

_M32 = 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Inline WASM builder
# ---------------------------------------------------------------------------


def _uleb128(v: int) -> bytes:
    if v == 0:
        return bytes([0])
    result = []
    while v > 0:
        low7 = v & 0x7F
        v >>= 7
        if v > 0:
            low7 |= 0x80
        result.append(low7)
    return bytes(result)


def _section(sid: int, data: bytes) -> bytes:
    return bytes([sid]) + _uleb128(len(data)) + data


def make_add_wasm() -> bytes:
    """Return 0001-i32-add-wrap: (i32, i32) -> i32, body = local.get 0; local.get 1; i32.add; end."""
    I32 = 0x7F
    body = b"\x20\x00\x20\x01\x6A\x0B"  # local.get 0; local.get 1; i32.add; end
    type_body = bytes([1, 0x60, 2, I32, I32, 1, I32])
    func_body = bytes([1, 0])
    name = b"main"
    export_body = bytes([1]) + _uleb128(len(name)) + name + bytes([0, 0])
    func_bytes = bytes([0]) + body
    code_body = bytes([1]) + _uleb128(len(func_bytes)) + func_bytes
    return (
        b"\x00asm\x01\x00\x00\x00"
        + _section(1, type_body)
        + _section(3, func_body)
        + _section(7, export_body)
        + _section(10, code_body)
    )


# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------


@dataclass
class AlignmentMismatch:
    """One observable field that differed between source and BTOR2 at a step."""

    step: int
    label: str
    source_value: Any
    reasoning_value: Any

    def __str__(self) -> str:
        return (
            f"step {self.step}: {self.label}: "
            f"src={self.source_value!r} btor2={self.reasoning_value!r}"
        )


@dataclass
class AlignmentReport:
    """Full result of one oracle run."""

    outcome: str          # "agreement" | "divergence"
    steps_checked: int
    mismatches: list[AlignmentMismatch] = field(default_factory=list)

    @property
    def agrees(self) -> bool:
        return self.outcome == "agreement"

    def summary(self) -> str:
        if self.agrees:
            return f"agreement over {self.steps_checked} steps"
        first = self.mismatches[0].step
        n = len(self.mismatches)
        lines = [f"divergence at step {first} ({n} mismatch(es)):"]
        for m in self.mismatches[:5]:
            lines.append(f"  {m}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Oracle implementation
# ---------------------------------------------------------------------------


def _make_annotator() -> AnnotationEmitter:
    sidecar = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="")
    return AnnotationEmitter(sidecar)


def run_oracle(
    params: Sequence[int],
    *,
    bound: int = 8,
    wasm_bytes: bytes | None = None,
    entry_name: str = "main",
) -> AlignmentReport:
    """Check step-by-step alignment for the given concrete parameter values.

    Compiles ``wasm_bytes`` (defaulting to the 0001-i32-add-wrap module) to
    a BTOR2 artifact, runs the source interpreter and the BTOR2 reasoning
    interpreter with the same concrete ``params``, then compares local-
    variable state and the trap flag at every step up to the source trace's
    length.

    Returns ``AlignmentReport(outcome="agreement", ...)`` when every
    observable agrees, or ``AlignmentReport(outcome="divergence", ...)``
    listing the first mismatches.
    """
    if wasm_bytes is None:
        wasm_bytes = make_add_wasm()

    source = load_wasm_source(wasm_bytes)
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="oracle.wasm"),
        scope=AnalysisScope(entry_function=entry_name),
        question=QuestionSpec(kind=PropertyKind.REACH_TRAP),
    )
    artifact = Translator().translate(spec, source, _make_annotator())

    # Build symbol→nid map for state lookup.
    parsed = btor2_parse(artifact.flattened.decode("utf-8"))
    sym_to_nid: dict[str, int] = {
        n.symbol: n.nid
        for n in parsed.model.nodes()
        if n.op == "state" and n.symbol
    }
    local_syms = sorted(
        [s for s in sym_to_nid if s.startswith("local_")],
        key=lambda s: int(s.split("_")[1]),
    )
    n_locals = len(local_syms)
    n_params = len(params)

    # Source interpreter: shadow mode so we can track local writes per step.
    src_binding = WasmInputBinding(param_init={k: int(v) for k, v in enumerate(params)})
    src_trace = WasmSourceInterpreter().run(
        source,
        src_binding,
        max_steps=bound,
        entry_name=entry_name,
        record_shadow=True,
    )

    # Reasoning interpreter: override local initial state with concrete params.
    # The BTOR2 init clauses tie local_k to param_k_init input nodes; the
    # reasoning interpreter evaluates those with no bindings (→ 0), then
    # state_init_by_symbol overrides supply the actual concrete values.
    rbinding = Btor2ReasoningBinding(
        state_init_by_symbol={
            f"local_{k}": int(params[k]) & _M32 for k in range(n_params)
        },
    )
    r_trace = Btor2ReasoningInterpreter().run(artifact, rbinding, max_steps=bound)

    # Reconstruct source local state by starting from initial param values
    # and applying shadow local_write deltas step by step.
    src_locals: list[int] = [
        int(params[k]) & _M32 if k < n_params else 0 for k in range(n_locals)
    ]
    src_trap = 0

    steps_checked = min(len(src_trace.steps), len(r_trace.steps))
    mismatches: list[AlignmentMismatch] = []

    for i in range(steps_checked):
        src_step = src_trace.steps[i]
        r_step = r_trace.steps[i]

        # Apply local writes recorded by shadow mode.
        if src_step.deltas and "local_write" in src_step.deltas:
            idx, _old, new_val = src_step.deltas["local_write"]
            if 0 <= idx < n_locals:
                src_locals[idx] = int(new_val) & _M32

        # Source trap: the run() loop appends SourceStep(halted=True) only
        # when a WasmTrap exception is raised (unreachable, div-by-zero, OOB).
        if src_step.halted:
            src_trap = 1

        r_machine = r_step.layer_values.get("machine", {})

        # Compare trap flag.
        trap_nid = sym_to_nid.get("trap")
        if trap_nid is not None:
            r_trap = int(r_machine.get(trap_nid, 0))
            if r_trap != src_trap:
                mismatches.append(AlignmentMismatch(i, "trap", src_trap, r_trap))

        # Compare each local variable.
        for k, sym in enumerate(local_syms):
            nid = sym_to_nid[sym]
            r_val = int(r_machine.get(nid, 0)) & _M32
            s_val = src_locals[k]
            if r_val != s_val:
                mismatches.append(AlignmentMismatch(i, sym, s_val, r_val))

    return AlignmentReport(
        outcome="agreement" if not mismatches else "divergence",
        steps_checked=steps_checked,
        mismatches=mismatches,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> tuple[list[int], int, bool]:
    import argparse

    p = argparse.ArgumentParser(description="wasm-btor2 alignment oracle (P5)")
    p.add_argument("--params", nargs="+", type=int, default=None,
                   help="concrete parameter values (default: run built-in suite)")
    p.add_argument("--bound", type=int, default=8,
                   help="max steps per interpreter (default: 8)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    return args.params, args.bound, args.verbose


def main(argv: list[str] | None = None) -> None:
    """Run the alignment oracle on a suite of concrete inputs and report."""
    params_arg, bound, verbose = _parse_args(argv or sys.argv[1:])

    if params_arg is not None:
        cases: list[tuple[tuple[int, ...], str]] = [
            (tuple(params_arg), " + ".join(map(str, params_arg))),
        ]
    else:
        cases = [
            ((0, 0), "0 + 0 = 0"),
            ((3, 5), "3 + 5 = 8"),
            ((1, -1), "1 + (-1) = 0 (wrap)"),
            ((0x7FFFFFFF, 1), "INT32_MAX + 1 wraps"),
            ((0xFFFFFFFF, 0xFFFFFFFF), "-1 + -1 = -2 (wrap)"),
        ]

    all_ok = True
    for params, label in cases:
        report = run_oracle(params, bound=bound)
        status = "OK  " if report.agrees else "FAIL"
        if not report.agrees:
            all_ok = False
        print(f"[{status}] {label}: {report.summary()}")
        if verbose and report.mismatches:
            for m in report.mismatches:
                print(f"       {m}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
