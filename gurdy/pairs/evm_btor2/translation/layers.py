"""Per-layer emission helpers for the evm-btor2 translator (P4).

``emit_context_inputs`` declares the symbolic per-invocation context
variables (SCHEMA.md §4) as states held constant across all BMC steps
and wires spec assumptions (CallerPin, CallvaluePin, etc.) as
BTOR2 constraint nodes.

``emit_init_clauses`` wires zero-init for all scalar machine states
(SCHEMA.md §3.1) and applies GasLimitPin, StoragePin, and StorageWarm
assumptions from the spec.

Both functions take a fully-initialised ``Btor2Builder`` (sorts and
machine states already declared via ``emit_header`` + ``emit_machine_states``).
"""

from __future__ import annotations

from gurdy.pairs.evm_btor2.spec import (
    CallerPin,
    CalldataBytePin,
    CalldatasizePin,
    CallvaluePin,
    GasLimitPin,
    OriginPin,
    StoragePin,
    StorageWarm,
)
from gurdy.pairs.evm_btor2.translation.builder import Btor2Builder


# ---------------------------------------------------------------------------
# Context-variable catalogue (SCHEMA.md §4)
# ---------------------------------------------------------------------------

# (symbol, sort_name)
CONTEXT_VARS: tuple[tuple[str, str], ...] = (
    ("caller",       "bv256"),
    ("callvalue",    "bv256"),
    ("origin",       "bv256"),
    ("gasprice",     "bv256"),
    ("calldata",     "mem_t"),
    ("calldatasize", "bv256"),
    ("blocknumber",  "bv256"),
    ("timestamp",    "bv256"),
    ("prevrandao",   "bv256"),
    ("gaslimit",     "bv256"),
    ("coinbase",     "bv256"),
    ("basefee",      "bv256"),
    ("chainid",      "bv256"),
)

# Scalar machine states that get an explicit zero init (SCHEMA.md §3.1).
# Array states (stack, mem, sto, sto_warm, returndata) require a
# step-0 encoding not yet implemented in the P4 skeleton; they are
# left unconstrained at step 0 (default-zero in the evaluator).
_SCALAR_ZERO_INIT_STATES: tuple[tuple[str, str], ...] = (
    ("sp",             "bv10"),
    ("mem_words",      "bv256"),
    ("pc",             "bv16"),
    ("trap",           "bv1"),
    ("halted",         "bv1"),
    ("returndatasize", "bv256"),
)


# ---------------------------------------------------------------------------
# emit_context_inputs
# ---------------------------------------------------------------------------


def emit_context_inputs(b: Btor2Builder, spec) -> dict[str, int]:
    """Declare symbolic per-invocation context state variables.

    Each context variable is a BTOR2 ``state`` that is held constant
    across all BMC steps by wiring ``next(var) = var``.

    Automatically emits:
    - Address-validity constraints: ``caller[255:160] == 0`` and
      ``origin[255:160] == 0`` (SCHEMA.md §4).
    - ChainID default: ``constraint(chainid == 1)`` unless the spec
      overrides it (no ChainID assumption type exists at schema v1.0.0;
      the default is always 1).

    Assumption types translated to BTOR2 ``constraint`` nodes:
    - ``CallerPin(address)``  → ``constraint(eq(caller,  address))``
    - ``CallvaluePin(value)`` → ``constraint(eq(callvalue, value))``
    - ``OriginPin(address)``  → ``constraint(eq(origin,  address))``
    - ``CalldatasizePin(sz)`` → ``constraint(eq(calldatasize, sz))``
    - ``CalldataBytePin(off, val)`` →
        ``constraint(eq(read(calldata, off), val))``

    Returns a mapping from context symbol to its state nid.
    """
    ctx_nids: dict[str, int] = {}

    b.comment("context inputs — SCHEMA.md §4")
    for sym, sort_name in CONTEXT_VARS:
        sort_nid = b.sort_nids[sort_name]
        nid = b._alloc()
        from gurdy.pairs.evm_btor2.btor2.nodes import Node
        b.model.append(Node(nid=nid, op="state", args=[str(sort_nid)], symbol=sym))
        ctx_nids[sym] = nid

    # next(context_var) = context_var — held constant across all steps.
    b.comment("context vars are invariant across steps")
    for sym, sort_name in CONTEXT_VARS:
        sort_nid = b.sort_nids[sort_name]
        b.emit_no_sort("next", sort_nid, ctx_nids[sym], ctx_nids[sym])

    # Address-validity constraints (SCHEMA.md §4):
    # caller[255:160] == 0  and  origin[255:160] == 0
    b.comment("address constraints — SCHEMA.md §4")
    for addr_sym in ("caller", "origin"):
        addr_nid = ctx_nids[addr_sym]
        upper = b.slice("bv96", addr_nid, 255, 160)
        zero96 = b.const("bv96", 0)
        b.constraint(b.emit("eq", "bv1", upper, zero96))

    # ChainID default = 1 (SCHEMA.md §4, no override in v1.0.0 schema).
    b.comment("chainid default = 1")
    chain_val = b.const("bv256", 1)
    b.constraint(b.emit("eq", "bv1", ctx_nids["chainid"], chain_val))

    # Spec assumption constraints.
    b.comment("spec assumption constraints")
    for asm in getattr(spec, "assumptions", ()):
        if isinstance(asm, CallerPin):
            pin_val = b.const("bv256", asm.address)
            b.constraint(b.emit("eq", "bv1", ctx_nids["caller"], pin_val))

        elif isinstance(asm, CallvaluePin):
            pin_val = b.const("bv256", asm.value)
            b.constraint(b.emit("eq", "bv1", ctx_nids["callvalue"], pin_val))

        elif isinstance(asm, OriginPin):
            pin_val = b.const("bv256", asm.address)
            b.constraint(b.emit("eq", "bv1", ctx_nids["origin"], pin_val))

        elif isinstance(asm, CalldatasizePin):
            pin_val = b.const("bv256", asm.size)
            b.constraint(b.emit("eq", "bv1", ctx_nids["calldatasize"], pin_val))

        elif isinstance(asm, CalldataBytePin):
            offset_nid = b.const("bv256", asm.offset)
            byte_val = b.const("bv8", asm.value)
            read_nid = b.read("bv8", ctx_nids["calldata"], offset_nid)
            b.constraint(b.emit("eq", "bv1", read_nid, byte_val))

    return ctx_nids


# ---------------------------------------------------------------------------
# emit_init_clauses
# ---------------------------------------------------------------------------


def emit_init_clauses(b: Btor2Builder, spec, machine_nids: dict[str, int]) -> None:
    """Wire initial values for machine states (SCHEMA.md §3.1 + §3.2).

    Scalar bitvec states receive a BTOR2 ``init`` node that pins them
    to zero at step 0 per the schema defaults.  ``gas`` receives an
    ``init`` from ``GasLimitPin`` if present; otherwise left free (the
    solver selects the initial gas, which is acceptable for SAT queries
    that don't constrain gas).

    Array states (``stack``, ``mem``, ``sto``, ``sto_warm``,
    ``returndata``) cannot be zero-initialised with a literal in
    standard BTOR2.  They are left without an explicit ``init`` node
    here (the evaluator defaults them to empty/zero; the full
    translator will add a step-0 constraint gate in P5).

    ``StoragePin`` assumptions are encoded as ``constraint`` nodes of
    the form ``read(sto, slot) == value`` — these hold at ALL steps,
    which is correct only for slots never written by the bytecode under
    analysis.  A step-0 guard will replace this in P5.

    ``StorageWarm`` assumptions are encoded as ``constraint`` nodes of
    the form ``read(sto_warm, slot) == 1``.
    """
    b.comment("init clauses — SCHEMA.md §3.1")

    # Scalar bitvec zero inits.
    for sym, sort_name in _SCALAR_ZERO_INIT_STATES:
        if sym not in machine_nids:
            continue
        sort_nid = b.sort_nids[sort_name]
        zero_nid = b.const(sort_name, 0)
        b.emit_no_sort("init", sort_nid, machine_nids[sym], zero_nid)

    # Gas: GasLimitPin → init to pin value; else free.
    gas_pinned = False
    for asm in getattr(spec, "assumptions", ()):
        if isinstance(asm, GasLimitPin):
            gas_nid = b.const("bv64", asm.gas)
            b.emit_no_sort("init", b.sort_nids["bv64"], machine_nids["gas"], gas_nid)
            gas_pinned = True
            break
    if not gas_pinned:
        b.comment("gas: no GasLimitPin — initial gas is free (solver-chosen)")

    # StoragePin: constraint read(sto, slot) == value for each pin.
    sto_nid = machine_nids.get("sto")
    if sto_nid is not None:
        b.comment("StoragePin constraints on sto (all-steps; step-0 guard deferred to P5)")
        for asm in getattr(spec, "assumptions", ()):
            if isinstance(asm, StoragePin):
                slot_nid = b.const("bv256", asm.slot)
                val_nid = b.const("bv256", asm.value)
                read_nid = b.read("bv256", sto_nid, slot_nid)
                b.constraint(b.emit("eq", "bv1", read_nid, val_nid))

    # StorageWarm: constraint read(sto_warm, slot) == 1.
    sto_warm_nid = machine_nids.get("sto_warm")
    if sto_warm_nid is not None:
        for asm in getattr(spec, "assumptions", ()):
            if isinstance(asm, StorageWarm):
                slot_nid = b.const("bv256", asm.slot)
                one256 = b.const("bv256", 1)
                read_nid = b.read("bv256", sto_warm_nid, slot_nid)
                b.constraint(b.emit("eq", "bv1", read_nid, one256))


__all__ = [
    "CONTEXT_VARS",
    "emit_context_inputs",
    "emit_init_clauses",
]
