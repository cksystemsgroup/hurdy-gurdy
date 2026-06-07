"""Multi-step BTOR2 evaluator for the evm-btor2 pair.

Wraps the single-cycle ``evaluate`` into a multi-step, deterministic
transition-system evaluator. Returns a framework ``ReasoningTrace``
whose ``layer_values`` carries the state nids per step.

Adapted from riscv-btor2's Btor2ReasoningInterpreter; PAIR_ID and
INTERPRETER_VERSION updated for evm-btor2.  The BTOR2 evaluator and
parser are pulled from ``gurdy.pairs.evm_btor2.btor2``.

INTERPRETER_VERSION tracks fidelity to the evm-btor2 SCHEMA.md.
The first version (1.0.0) handles the bv256/bv8/bv10/bv64/bv1
sorts and the array sorts defined in SCHEMA.md §2.
"""

from __future__ import annotations

from typing import Any, Mapping

from gurdy.core.interp.types import ReasoningStep, ReasoningTrace
from gurdy.core.pair import CompiledArtifact
from gurdy.pairs.evm_btor2.btor2.evaluator import evaluate
from gurdy.pairs.evm_btor2.btor2.nodes import Model
from gurdy.pairs.evm_btor2.btor2.parser import from_text


INTERPRETER_VERSION = "1.0.0"
PAIR_ID = "evm-btor2"


class Btor2ReasoningInterpreter:
    """``ReasoningInterpreter`` Protocol implementation for evm-btor2."""

    version: str = INTERPRETER_VERSION

    def run(
        self,
        artifact: CompiledArtifact,
        binding: Any,  # Btor2ReasoningBinding (typed in bindings.py)
        max_steps: int,
    ) -> ReasoningTrace:
        text = artifact.flattened.decode("utf-8", errors="replace")
        parsed = from_text(text)
        model = parsed.model

        sym_to_nid = self._state_symbols(model)
        next_by_state = self._next_clauses(model)
        init_by_state = self._init_clauses(model)
        bad_exprs = self._bad_exprs(model)
        input_sym_to_nid = self._input_symbols(model)

        state_values: dict[int, Any] = {}
        binding_states: Mapping[str, Any] = getattr(
            binding, "state_init_by_symbol", {}
        ) or {}
        for nid, init_nid in init_by_state.items():
            init_vals = evaluate(model, bindings={})
            state_values[nid] = init_vals.get(init_nid, 0)
        for sym, val in binding_states.items():
            nid = sym_to_nid.get(sym)
            if nid is not None:
                state_values[nid] = val

        steps: list[ReasoningStep] = []
        bad_fired_at: int | None = None
        per_step_inputs = getattr(binding, "input_per_step_by_symbol", ()) or ()

        for i in range(max_steps):
            cycle_bindings: dict[int, Any] = dict(state_values)
            if i < len(per_step_inputs):
                for sym, val in (per_step_inputs[i] or {}).items():
                    nid = input_sym_to_nid.get(sym)
                    if nid is not None:
                        cycle_bindings[nid] = val

            values = evaluate(model, bindings=cycle_bindings)

            new_state_values: dict[int, Any] = {}
            for state_nid, next_value_nid in next_by_state.items():
                new_state_values[state_nid] = values.get(next_value_nid, 0)
            for state_nid, val in state_values.items():
                if state_nid not in new_state_values:
                    new_state_values[state_nid] = val

            symbol_view: dict[int, Any] = {}
            for sym, nid in sym_to_nid.items():
                symbol_view[nid] = new_state_values.get(nid, 0)
            step_layers = {"machine": symbol_view}

            fired_here = False
            if bad_fired_at is None and bad_exprs:
                post_values = evaluate(model, bindings=dict(new_state_values))
                for bad_nid_expr in bad_exprs:
                    v = post_values.get(bad_nid_expr, 0)
                    if isinstance(v, int) and v != 0:
                        bad_fired_at = i
                        fired_here = True
                        break

            steps.append(
                ReasoningStep(
                    step=i,
                    layer_values=step_layers,
                    bad_fired=fired_here,
                )
            )

            state_values = new_state_values

        artifact_hash = self._artifact_hash(artifact)
        bindings_hash = (
            binding.bindings_hash()
            if hasattr(binding, "bindings_hash")
            else ""
        )
        return ReasoningTrace(
            pair=PAIR_ID,
            interpreter_version=INTERPRETER_VERSION,
            artifact_hash=artifact_hash,
            bindings_hash=bindings_hash,
            steps=tuple(steps),
            bad_fired_at=bad_fired_at,
        )

    # ------------------------------------------------------------------

    def _state_symbols(self, model: Model) -> dict[str, int]:
        out: dict[str, int] = {}
        for n in model.nodes():
            if n.op == "state" and n.symbol:
                out[n.symbol] = n.nid
        return out

    def _input_symbols(self, model: Model) -> dict[str, int]:
        out: dict[str, int] = {}
        for n in model.nodes():
            if n.op == "input" and n.symbol:
                out[n.symbol] = n.nid
        return out

    def _next_clauses(self, model: Model) -> dict[int, int]:
        out: dict[int, int] = {}
        for n in model.nodes():
            if n.op == "next" and len(n.args) >= 3:
                state_nid = int(n.args[1])
                value_nid = int(n.args[2])
                out[state_nid] = value_nid
        return out

    def _init_clauses(self, model: Model) -> dict[int, int]:
        out: dict[int, int] = {}
        for n in model.nodes():
            if n.op == "init" and len(n.args) >= 3:
                state_nid = int(n.args[1])
                value_nid = int(n.args[2])
                out[state_nid] = value_nid
        return out

    def _bad_exprs(self, model: Model) -> list[int]:
        out: list[int] = []
        for n in model.nodes():
            if n.op == "bad" and len(n.args) >= 1:
                out.append(int(n.args[0]))
        return out

    def _artifact_hash(self, artifact: CompiledArtifact) -> str:
        import hashlib
        return hashlib.sha256(artifact.flattened).hexdigest()


__all__ = ["Btor2ReasoningInterpreter", "INTERPRETER_VERSION"]
