"""Witness lifter: z3 model text + BTOR2 artifact → WasmWitness.

The BMC unroller in ``solvers._bmc`` names variables::

    s{cycle}_n{nid}   — state variable for BTOR2 node ``nid`` at BMC cycle
    in{cycle}_n{nid}  — input variable for BTOR2 node ``nid`` at BMC cycle

The BTOR2 flattened text associates symbolic names with nids::

    25 state 3 local_0
    26 input 3 param_0_init
    27 state 1 trap

``lift_witness`` correlates those two sources to populate ``WasmWitness``.
"""

from __future__ import annotations

from gurdy.pairs.wasm_btor2.lift.parse_z3_model import parse_z3_model
from gurdy.pairs.wasm_btor2.lift.witness import WasmWitness

_MAX_CYCLES = 256  # upper bound when scanning for trap step


def _build_symbol_map(btor2_text: str) -> dict[int, str]:
    """Return {nid: symbol} for every state/input node that has a symbol."""
    result: dict[int, str] = {}
    for raw_line in btor2_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(';'):
            continue
        parts = line.split()
        # format: nid op sort_nid [symbol]  — symbol is the 4th token
        if len(parts) >= 4 and parts[1] in ('state', 'input'):
            try:
                nid = int(parts[0])
            except ValueError:
                continue
            result[nid] = parts[3]
    return result


def lift_witness(
    btor2_flattened: str | bytes,
    witness_text: str,
) -> WasmWitness:
    """Extract a ``WasmWitness`` from a z3 model string and a BTOR2 artifact.

    Args:
        btor2_flattened: the flattened BTOR2 text (``CompiledArtifact.flattened``).
            Used to build the nid → symbol map.
        witness_text: ``str(z3_solver.model())`` from ``Z3BMCSolver.dispatch``
            payload (``result.payload["witness_text"]``).

    Returns:
        A ``WasmWitness`` with concrete parameter values and trap step.
        Fields are left at their defaults (empty dict / None / 0) when the
        information is absent from the witness.
    """
    if isinstance(btor2_flattened, bytes):
        btor2_flattened = btor2_flattened.decode('utf-8')

    sym_map = _build_symbol_map(btor2_flattened)
    nid_for_sym: dict[str, int] = {v: k for k, v in sym_map.items()}
    z3_vals = parse_z3_model(witness_text)

    # --- parameter extraction ---
    # param_k_init is an *input* node; the BMC names it in0_n{nid} at cycle 0.
    # The init clause equates local_k@0 with param_k_init@0, so s0_n{local_nid}
    # carries the same value and serves as a fallback.
    params: dict[int, int] = {}
    k = 0
    while True:
        param_sym = f'param_{k}_init'
        if param_sym not in nid_for_sym:
            break
        param_nid = nid_for_sym[param_sym]
        primary = f'in0_n{param_nid}'
        if primary in z3_vals:
            params[k] = z3_vals[primary] & 0xFFFFFFFF
        else:
            local_sym = f'local_{k}'
            if local_sym in nid_for_sym:
                fallback = f's0_n{nid_for_sym[local_sym]}'
                if fallback in z3_vals:
                    params[k] = z3_vals[fallback] & 0xFFFFFFFF
        k += 1
    n_params = k

    # --- trap step extraction ---
    trap_step: int | None = None
    if 'trap' in nid_for_sym:
        trap_nid = nid_for_sym['trap']
        for cycle in range(_MAX_CYCLES):
            var = f's{cycle}_n{trap_nid}'
            if var in z3_vals and z3_vals[var] != 0:
                trap_step = cycle
                break

    return WasmWitness(params=params, trap_step=trap_step, n_params=n_params)


__all__ = ["lift_witness"]
