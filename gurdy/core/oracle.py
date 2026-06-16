"""The Oracle protocol — a registered formal model's reference interface.

A model registered in ``registry/models/<id>.yaml`` is made real by an Oracle
that backs some subset of three capabilities. A pair that references the model
can reach a fidelity bounded by the model's *certified* capabilities (the model
gate decides which are backed; see ``gate/model``). Smallest-useful-first:

  EXECUTABLE    ``run(program, binding) -> projection``     (=> F1/F2 for pairs)
  PROOF_EXPORT  a transcribable / mechanized reference       (=> F3/F4)
  MACHINE_GEN   a verified BTOR2 machine model               (=> the machine path)

Lean by design (ROADMAP MA2): exactly these three strings; add another only when
a concrete model needs it. One backend today (``kind: sail``); ``build_oracle``
raises for any other so a new backend is an explicit, reviewed addition.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

EXECUTABLE = "executable"
PROOF_EXPORT = "proof_export"
MACHINE_GEN = "machine_gen"
ALL_CAPABILITIES = (EXECUTABLE, PROOF_EXPORT, MACHINE_GEN)


@runtime_checkable
class Oracle(Protocol):
    """What a registered model provides as a reference. ``run`` (EXECUTABLE) is
    required of every model; ``reference_export`` (PROOF_EXPORT) and
    ``machine_model`` (MACHINE_GEN) are present iff the model declares them."""

    def capabilities(self) -> frozenset[str]: ...

    def run(self, program: Any, binding: dict | None = None, *, max_steps: int = 64) -> Any: ...


class _SailOracle:
    """Thin adapter: the pinned Sail-RISC-V emulator behind the Oracle protocol.

    ``run`` delegates to the existing emulator realization (no behavior change).
    ``reference_export`` returns the transcribed reference that backs proof_export;
    ``machine_model`` returns the verified BTOR2 machine that backs machine_gen.
    All heavy imports are lazy so importing this module is cheap and cycle-free.
    """

    kind = "sail"

    def __init__(self, model_id: str, language: str, capabilities: frozenset[str], group: str):
        self.model_id = model_id
        self.language = language
        self.group = group
        self._caps = frozenset(capabilities)

    def capabilities(self) -> frozenset[str]:
        return self._caps

    def _emulator(self):
        from tools.sail_btor2_machine import sail_cross
        return sail_cross._load_oracle()

    def available(self) -> bool:
        """True iff the pinned emulator binary is reachable in this environment."""
        try:
            return bool(self._emulator().available())
        except Exception:
            return False

    def run(self, program: bytes, binding: dict | None = None, *, max_steps: int = 64):
        return self._emulator().run(program, binding, max_steps=max_steps)

    def reference_export(self):
        """PROOF_EXPORT backing: the transcribed, Sail-cross-validated reference."""
        from tools.sail_btor2_machine.verify import _load_reference
        return _load_reference()

    def machine_model(self):
        """MACHINE_GEN backing: generate + verify the BTOR2 machine (a report)."""
        from gate.machine.verify_machine import gate_machine
        return gate_machine(self.group)


def build_oracle(reg) -> Oracle:
    """Construct the Oracle for a model registration (``gurdy.core.model``).

    Lean: one backend today. Unknown kinds raise — a new backend (external
    interpreter, KEVM, WasmCert, …) is an explicit adapter added here."""
    caps = frozenset(reg.target_capabilities)
    if reg.oracle_kind == "sail":
        return _SailOracle(reg.id, reg.language, caps, group=reg.group)
    raise NotImplementedError(
        f"oracle kind {reg.oracle_kind!r} for model {reg.id!r} is not supported yet "
        f"(only 'sail'); add an adapter in gurdy/core/oracle.py")
