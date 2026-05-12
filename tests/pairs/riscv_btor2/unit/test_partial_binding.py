"""Phase 3: ``FREE`` sentinel and plain-interpreter rejection.

SCHEMA.md §14.2. Tests the binding-level type vocabulary and that
:class:`RiscvSourceInterpreter` raises a clean diagnostic on any
free field. The term-shadow interpreter (which accepts free fields)
lands in Phase 4.
"""

from __future__ import annotations

import pytest

from gurdy.pairs.riscv_btor2.source_interp.bindings import (
    FREE,
    Free,
    FreeFieldNotAllowed,
    RiscvInputBinding,
)
from gurdy.pairs.riscv_btor2.source_interp.interpreter import (
    RiscvSourceInterpreter,
)


# ---------------------------------------------------------------------------
# Sentinel semantics
# ---------------------------------------------------------------------------


def test_free_is_singleton():
    assert Free() is FREE
    assert isinstance(FREE, Free)
    assert FREE == Free()


def test_free_hash_stable():
    {FREE: 1}[FREE] == 1
    assert hash(FREE) == hash(Free())


def test_repr_serialization():
    assert repr(FREE) == "Free"


# ---------------------------------------------------------------------------
# Binding round-trip with FREE
# ---------------------------------------------------------------------------


def test_binding_has_free_fields_reflects_state():
    pinned = RiscvInputBinding(register_init={1: 10, 2: 20})
    assert pinned.has_free_fields() is False
    partial = RiscvInputBinding(register_init={1: 10, 2: FREE})
    assert partial.has_free_fields() is True
    mem = RiscvInputBinding(memory_init={0x100: FREE})
    assert mem.has_free_fields() is True
    havoc = RiscvInputBinding(havoc_per_step=({1: FREE},))
    assert havoc.has_free_fields() is True


def test_binding_json_round_trips_with_free():
    b = RiscvInputBinding(
        register_init={1: 10, 2: FREE},
        memory_init={0x100: FREE, 0x101: 0xFF},
        havoc_per_step=({1: FREE, 2: 99},),
    )
    obj = b.to_jsonable()
    rebuilt = RiscvInputBinding.from_jsonable(obj)
    assert rebuilt.register_init == {1: 10, 2: FREE}
    assert rebuilt.memory_init == {0x100: FREE, 0x101: 0xFF}
    assert rebuilt.havoc_per_step[0] == {1: FREE, 2: 99}
    # Hash is stable across round-trip.
    assert b.inputs_hash() == rebuilt.inputs_hash()


def test_binding_with_and_without_free_hash_differently():
    b1 = RiscvInputBinding(register_init={1: 10})
    b2 = RiscvInputBinding(register_init={1: FREE})
    assert b1.inputs_hash() != b2.inputs_hash()


# ---------------------------------------------------------------------------
# Plain interpreter rejection
# ---------------------------------------------------------------------------


def test_plain_interpreter_rejects_free_register():
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding(register_init={1: FREE})
    # source / max_steps are irrelevant — the check fires before any decode.
    with pytest.raises(FreeFieldNotAllowed):
        interp.run(source=None, binding=binding, max_steps=10)  # type: ignore[arg-type]


def test_plain_interpreter_rejects_free_memory():
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding(memory_init={0x1000: FREE})
    with pytest.raises(FreeFieldNotAllowed):
        interp.run(source=None, binding=binding, max_steps=10)  # type: ignore[arg-type]


def test_plain_interpreter_rejects_free_havoc():
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding(havoc_per_step=({1: FREE},))
    with pytest.raises(FreeFieldNotAllowed):
        interp.run(source=None, binding=binding, max_steps=10)  # type: ignore[arg-type]


def test_plain_interpreter_accepts_fully_pinned_binding():
    """Sanity: no FREE → no rejection (the v1.0.0 path is intact)."""
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding(register_init={1: 0x10, 2: 0x20})
    assert binding.has_free_fields() is False
    # We're not actually running a program here, just ensuring the
    # FreeFieldNotAllowed gate doesn't fire. The interpreter will
    # crash on `source=None` later, but that's a separate concern.
    with pytest.raises(Exception) as excinfo:
        interp.run(source=None, binding=binding, max_steps=1)  # type: ignore[arg-type]
    assert not isinstance(excinfo.value, FreeFieldNotAllowed)
