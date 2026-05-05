"""Multi-step BTOR2 evaluator wrapping the single-cycle ``evaluate``.

The single-cycle evaluator computes node values for one step given
state and input bindings. To run a transition system across multiple
steps we:

1. Parse the artifact's flattened text once.
2. Build an index from state nids to their ``next`` clauses (operand
   carrying the next-cycle value) and from state symbols to nids.
3. For step 0, take initial state values from ``init`` clauses where
   present, overridden by the binding's ``state_init_by_symbol``.
4. For each step, run the single-cycle evaluator with the current
   state values; read the ``next`` operand for each state to get the
   step's output (= step+1's input). Check every ``bad`` clause and
   record the first step where any fires.

This is purely mechanical: same artifact + same binding → identical
trace. No search, no symbolic state.
"""

from __future__ import annotations

from typing import Any, Mapping

from gurdy.core.interp.types import ReasoningStep, ReasoningTrace
from gurdy.core.pair import CompiledArtifact
from gurdy.pairs.riscv_btor2.btor2.evaluator import evaluate
from gurdy.pairs.riscv_btor2.btor2.nodes import Model
from gurdy.pairs.riscv_btor2.btor2.parser import from_text


INTERPRETER_VERSION = "1.0.0"
PAIR_ID = "riscv-btor2"


class Btor2ReasoningInterpreter:
    """``ReasoningInterpreter`` Protocol implementation for riscv-btor2."""

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

        # Step-0 state values: from binding overrides, then init clauses,
        # then defaults computed by single-cycle evaluator (zero).
        state_values: dict[int, Any] = {}
        binding_states: Mapping[str, Any] = getattr(
            binding, "state_init_by_symbol", {}
        ) or {}
        for nid, init_nid in init_by_state.items():
            # Evaluate the init expression with no bindings (constants/computations).
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
            # Build the per-step bindings: states + per-step inputs.
            cycle_bindings: dict[int, Any] = dict(state_values)
            if i < len(per_step_inputs):
                for sym, val in (per_step_inputs[i] or {}).items():
                    nid = input_sym_to_nid.get(sym)
                    if nid is not None:
                        cycle_bindings[nid] = val
            values = evaluate(model, bindings=cycle_bindings)

            # Compute next-cycle state values from `next` clauses, carrying
            # forward states without one.
            new_state_values: dict[int, Any] = {}
            for state_nid, next_value_nid in next_by_state.items():
                new_state_values[state_nid] = values.get(next_value_nid, 0)
            for state_nid, val in state_values.items():
                if state_nid not in new_state_values:
                    new_state_values[state_nid] = val

            # Record POST-step state (matches the source interpreter's
            # deltas convention so cross_check aligns).
            symbol_view: dict[int, Any] = {}
            for sym, nid in sym_to_nid.items():
                symbol_view[nid] = new_state_values.get(nid, 0)
            step_layers = {"machine": symbol_view}

            # Bad-firing check on the *post-step* state. Re-evaluates
            # the model with the new state values so that ``bad`` is
            # observed in the same state ``layer_values`` reports.
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
