"""Witness lifter: z3 model text + BTOR2 artifact → EbpfWitness.

The shared BMC unroller (``gurdy.core.btor2._bmc``) names variables::

    s{cycle}_n{nid}   — state variable for BTOR2 node ``nid`` at BMC cycle
    in{cycle}_n{nid}  — input variable for BTOR2 node ``nid`` at BMC cycle

The flattened BTOR2 text associates symbolic names with nids; the
ebpf-btor2 ``machine`` layer declares ``reg_r0``…``reg_r9``, ``insn_idx``,
and ``halted``. ``lift_witness`` correlates the two sources to recover
the concrete entry register values and the exit (halt) cycle.

A small self-contained z3-model value parser keeps this pair independent
of every other pair (pairs share the framework, not each other's code).
"""

from __future__ import annotations

import re

from gurdy.pairs.ebpf_btor2.lift.witness import EbpfWitness

_MAX_CYCLES = 256  # upper bound when scanning for the halt cycle
_MASK64 = (1 << 64) - 1
_NUM_REGS = 10  # reg_r0..reg_r9 are state; r10 (stack ptr) is not modelled here


_ASSIGNMENT_RE = re.compile(
    r"(?:^|[\[,\s])"
    r"([A-Za-z_][A-Za-z0-9_!]*)"  # variable name (z3 uses ! in some suffixes)
    r"\s*=\s*"
    r"(#x[0-9a-fA-F]+"   # SMT-LIB hex
    r"|#b[01]+"          # SMT-LIB binary
    r"|0x[0-9a-fA-F]+"   # C-style hex
    r"|-?\d+)"           # signed decimal
)


def _parse_z3_model(witness_text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in _ASSIGNMENT_RE.finditer(witness_text):
        name, raw = m.group(1), m.group(2)
        if raw.startswith("#x") or raw.startswith("0x"):
            val = int(raw[2:], 16)
        elif raw.startswith("#b"):
            val = int(raw[2:], 2)
        else:
            val = int(raw)
        out[name] = val
    return out


def _build_symbol_map(btor2_text: str) -> dict[str, int]:
    """Return {symbol: nid} for every state/input node that has a symbol."""
    nid_for_sym: dict[str, int] = {}
    for raw_line in btor2_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split()
        # nid op sort_nid [symbol]
        if len(parts) >= 4 and parts[1] in ("state", "input"):
            try:
                nid = int(parts[0])
            except ValueError:
                continue
            nid_for_sym[parts[3]] = nid
    return nid_for_sym


def lift_witness(
    btor2_flattened: str | bytes,
    witness_text: str,
    reachable: bool = True,
) -> EbpfWitness:
    """Recover an :class:`EbpfWitness` from a z3 model and a BTOR2 artifact.

    Returns an empty (``reachable=False``) witness when ``reachable`` is
    false or the model text is empty; missing fields default rather than
    raise, mirroring the wasm-btor2 lifter's behaviour.
    """
    if not reachable or not witness_text:
        return EbpfWitness(reachable=False)

    if isinstance(btor2_flattened, bytes):
        btor2_flattened = btor2_flattened.decode("utf-8")

    nid_for_sym = _build_symbol_map(btor2_flattened)
    z3_vals = _parse_z3_model(witness_text)

    initial_regs: dict[int, int] = {}
    for i in range(_NUM_REGS):
        nid = nid_for_sym.get(f"reg_r{i}")
        if nid is None:
            continue
        var = f"s0_n{nid}"
        if var in z3_vals:
            initial_regs[i] = z3_vals[var] & _MASK64

    halted_step: int | None = None
    halted_nid = nid_for_sym.get("halted")
    if halted_nid is not None:
        for cycle in range(_MAX_CYCLES):
            var = f"s{cycle}_n{halted_nid}"
            if var in z3_vals and z3_vals[var] != 0:
                halted_step = cycle
                break

    return EbpfWitness(
        reachable=True,
        initial_regs=initial_regs,
        halted_step=halted_step,
    )


__all__ = ["lift_witness"]
