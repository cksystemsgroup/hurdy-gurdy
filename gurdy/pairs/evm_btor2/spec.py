"""evm-btor2 spec language — schema v1.0.0.

Defines ``EvmBtor2Spec`` (a ``BaseSpec`` subclass) and the pair-specific
assumption / property / directive types described in SCHEMA.md. The
structural validator is registered as the pair's ``SpecValidator`` and
emits diagnostics for malformed specs without compiling.

Schema version: 1.0.0.
"""

from __future__ import annotations

import binascii
import enum
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from gurdy.core.diagnostics import Diagnostic, Severity
from gurdy.core.spec.base import (
    BaseAnalysisDirective,
    BaseAssumption,
    BaseProperty,
    BaseSpec,
)


PAIR_ID = "evm-btor2"
SCHEMA_VERSION = "1.0.0"

_BV256_MAX = (1 << 256) - 1
_BV64_MAX = (1 << 64) - 1
_ADDR_MAX = (1 << 160) - 1  # 20-byte Ethereum address


# ---------------------------------------------------------------------------
# EVM version
# ---------------------------------------------------------------------------


class EvmVersion(str, enum.Enum):
    LONDON = "london"      # EIP-1559, EIP-3198 BASEFEE
    PARIS = "paris"        # EIP-3675 PoS; DIFFICULTY → PREVRANDAO
    SHANGHAI = "shanghai"  # EIP-3855 PUSH0
    CANCUN = "cancun"      # EIP-4844 BLOBHASH / BLOBBASEFEE


# ---------------------------------------------------------------------------
# Bytecode reference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BytecodeRef:
    """Deployed EVM bytecode (SCHEMA.md §15.1)."""

    hex: str  # lowercase hex, no 0x prefix; must be even-length valid hex
    content_hash: str | None = None  # keccak256 of decoded bytes, hex


# ---------------------------------------------------------------------------
# Analysis scope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisScope:
    """EVM version gate and scope restrictions (SCHEMA.md §15.2).

    P1: pure-function subset — no CALL family, no CREATE, no
    SELFDESTRUCT. Single contract, single call, BMC engine.
    """

    evm_version: EvmVersion = EvmVersion.LONDON


# ---------------------------------------------------------------------------
# Assumptions (SCHEMA.md §15.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallerPin(BaseAssumption):
    """Constrain CALLER to a specific 20-byte Ethereum address."""

    address: int  # 0 ≤ address ≤ 2^160 − 1


@dataclass(frozen=True)
class CallvaluePin(BaseAssumption):
    """Constrain CALLVALUE (msg.value) in wei."""

    value: int  # 0 ≤ value ≤ 2^256 − 1


@dataclass(frozen=True)
class OriginPin(BaseAssumption):
    """Constrain ORIGIN (tx.origin) to a specific Ethereum address."""

    address: int  # 0 ≤ address ≤ 2^160 − 1


@dataclass(frozen=True)
class CalldatasizePin(BaseAssumption):
    """Constrain CALLDATASIZE to exactly this many bytes."""

    size: int  # 0 ≤ size ≤ 2^256 − 1


@dataclass(frozen=True)
class CalldataBytePin(BaseAssumption):
    """Constrain a single byte of calldata: calldata[offset] == value."""

    offset: int  # 0 ≤ offset ≤ 2^256 − 1
    value: int   # 0 ≤ value ≤ 255


@dataclass(frozen=True)
class StoragePin(BaseAssumption):
    """Set initial storage[slot] == value (before any SSTORE in this call)."""

    slot: int   # 0 ≤ slot ≤ 2^256 − 1
    value: int  # 0 ≤ value ≤ 2^256 − 1


@dataclass(frozen=True)
class StorageWarm(BaseAssumption):
    """Pre-warm a storage slot (EIP-2929 access set initialisation)."""

    slot: int  # 0 ≤ slot ≤ 2^256 − 1


@dataclass(frozen=True)
class GasLimitPin(BaseAssumption):
    """Constrain the initial gas available for execution."""

    gas: int  # 0 ≤ gas ≤ 2^64 − 1


# ---------------------------------------------------------------------------
# Property (SCHEMA.md §14 and §15.4)
# ---------------------------------------------------------------------------


class ReachKind(str, enum.Enum):
    REVERT = "revert"              # halted AND trap == 1
    STOP = "stop"                  # halted AND trap == 0
    STORAGE_EQ = "storage_eq"     # halted AND trap==0 AND sto[slot]==value
    RETURNDATA_EQ = "returndata_eq"  # halted AND trap==0 AND returndata matches


@dataclass(frozen=True)
class ReachProperty(BaseProperty):
    """BMC reachability property.

    ``bad`` fires when ``halted == 1`` and the reach condition holds.
    All conditions are evaluated post-halt (SCHEMA.md §14.1).
    """

    kind: ReachKind = ReachKind.REVERT
    # For STORAGE_EQ:
    slot: int | None = None   # storage slot index
    value: int | None = None  # expected storage value
    # For RETURNDATA_EQ:
    offset: int | None = None        # byte offset into returndata
    data: tuple[int, ...] | None = None  # expected bytes (each 0..255)


# ---------------------------------------------------------------------------
# Analysis directive (SCHEMA.md §15.5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisDirective(BaseAnalysisDirective):
    engine: str = "z3-bmc"
    bound: int | None = None    # max BMC steps; None → 100 (translator default)
    timeout: int | None = None  # seconds per solver call; None → solver default


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvmBtor2Spec(BaseSpec):
    """QuestionSpec for the evm-btor2 pair.

    Captures the bytecode under analysis, the scope (EVM version, pure-
    function subset), pin assumptions, the reach property to verify, and
    the solver directive.  Schema version 1.0.0 (SCHEMA.md).
    """

    pair = PAIR_ID  # class variable; not a dataclass field
    schema_version: str = SCHEMA_VERSION

    bytecode: BytecodeRef = field(default_factory=lambda: BytecodeRef(hex=""))
    scope: AnalysisScope = field(default_factory=AnalysisScope)
    assumptions: tuple[BaseAssumption, ...] = ()
    property: ReachProperty = field(default_factory=ReachProperty)
    analysis: AnalysisDirective = field(default_factory=AnalysisDirective)

    # ----- JSON round-trip -----

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "EvmBtor2Spec":
        if obj.get("pair") != PAIR_ID:
            raise ValueError(f"not a {PAIR_ID} spec: pair={obj.get('pair')!r}")
        f = obj.get("fields", {})
        bytecode = _bytecode_from(f.get("bytecode"))
        scope = _scope_from(f.get("scope"))
        assumptions = tuple(_asm_from(a) for a in f.get("assumptions", []))
        prop = _prop_from(f.get("property"))
        analysis = _analysis_from(f.get("analysis"))
        return cls(
            bytecode=bytecode,
            scope=scope,
            assumptions=assumptions,
            property=prop,
            analysis=analysis,
        )


# ---------- per-component decoders ----------


def _bytecode_from(obj: Any) -> BytecodeRef:
    if obj is None:
        return BytecodeRef(hex="")
    return BytecodeRef(
        hex=obj.get("hex", ""),
        content_hash=obj.get("content_hash"),
    )


def _scope_from(obj: Any) -> AnalysisScope:
    if obj is None:
        return AnalysisScope()
    raw_ver = obj.get("evm_version", "london")
    try:
        ver = EvmVersion(raw_ver)
    except ValueError:
        ver = EvmVersion.LONDON
    return AnalysisScope(evm_version=ver)


def _asm_from(obj: Any) -> BaseAssumption:
    t = obj.get("__type__", "")
    if t == "CallerPin":
        return CallerPin(address=int(obj["address"]))
    if t == "CallvaluePin":
        return CallvaluePin(value=int(obj["value"]))
    if t == "OriginPin":
        return OriginPin(address=int(obj["address"]))
    if t == "CalldatasizePin":
        return CalldatasizePin(size=int(obj["size"]))
    if t == "CalldataBytePin":
        return CalldataBytePin(offset=int(obj["offset"]), value=int(obj["value"]))
    if t == "StoragePin":
        return StoragePin(slot=int(obj["slot"]), value=int(obj["value"]))
    if t == "StorageWarm":
        return StorageWarm(slot=int(obj["slot"]))
    if t == "GasLimitPin":
        return GasLimitPin(gas=int(obj["gas"]))
    raise ValueError(f"unknown assumption type {t!r}")


def _prop_from(obj: Any) -> ReachProperty:
    if obj is None:
        return ReachProperty()
    kind = ReachKind(obj.get("kind", "revert"))
    slot = obj.get("slot")
    value = obj.get("value")
    offset = obj.get("offset")
    raw_data = obj.get("data")
    data: tuple[int, ...] | None = None
    if raw_data is not None:
        data = tuple(int(b) for b in raw_data)
    return ReachProperty(
        kind=kind,
        slot=int(slot) if slot is not None else None,
        value=int(value) if value is not None else None,
        offset=int(offset) if offset is not None else None,
        data=data,
    )


def _analysis_from(obj: Any) -> AnalysisDirective:
    if obj is None:
        return AnalysisDirective()
    return AnalysisDirective(
        engine=obj.get("engine", "z3-bmc"),
        bound=int(obj["bound"]) if obj.get("bound") is not None else None,
        timeout=int(obj["timeout"]) if obj.get("timeout") is not None else None,
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

_ALLOWED_ENGINES = frozenset({"z3-bmc"})


def _err(code: str, msg: str, **detail: Any) -> Diagnostic:
    return Diagnostic(Severity.ERROR, f"evm-btor2/spec/{code}", msg, detail=detail or None)


def validate_evm_btor2_spec(spec: EvmBtor2Spec, _source: Any = None) -> Iterable[Diagnostic]:
    """Structural validator for ``EvmBtor2Spec``.

    Does not compile.  ``_source`` is unused in P1 (no symbol table);
    present for interface parity with riscv-btor2.
    """
    diags: list[Diagnostic] = []

    if not isinstance(spec, EvmBtor2Spec):
        diags.append(_err("0001", "spec is not an EvmBtor2Spec"))
        return diags

    # --- bytecode ---
    if not spec.bytecode.hex:
        diags.append(_err("0010", "bytecode.hex is empty"))
    else:
        h = spec.bytecode.hex
        if len(h) % 2 != 0:
            diags.append(_err("0011", "bytecode.hex has odd length (not valid hex)"))
        else:
            try:
                binascii.unhexlify(h)
            except (ValueError, binascii.Error):
                diags.append(_err("0012", "bytecode.hex contains non-hex characters"))

    # --- scope ---
    if not isinstance(spec.scope.evm_version, EvmVersion):
        diags.append(_err("0020", f"scope.evm_version is not a valid EvmVersion: {spec.scope.evm_version!r}"))

    # --- assumptions ---
    seen_calldata_pins: dict[int, int] = {}  # offset → value (conflict detection)
    seen_storage_pins: set[int] = set()
    seen_caller = False
    seen_callvalue = False
    seen_origin = False
    seen_calldatasize = False
    seen_gas = False

    for i, asm in enumerate(spec.assumptions):
        if isinstance(asm, CallerPin):
            if seen_caller:
                diags.append(_err("0030", "duplicate CallerPin"))
            seen_caller = True
            if not 0 <= asm.address <= _ADDR_MAX:
                diags.append(_err("0031", f"CallerPin.address out of 160-bit range: {asm.address}"))

        elif isinstance(asm, CallvaluePin):
            if seen_callvalue:
                diags.append(_err("0032", "duplicate CallvaluePin"))
            seen_callvalue = True
            if not 0 <= asm.value <= _BV256_MAX:
                diags.append(_err("0033", f"CallvaluePin.value out of bv256 range: {asm.value}"))

        elif isinstance(asm, OriginPin):
            if seen_origin:
                diags.append(_err("0034", "duplicate OriginPin"))
            seen_origin = True
            if not 0 <= asm.address <= _ADDR_MAX:
                diags.append(_err("0035", f"OriginPin.address out of 160-bit range: {asm.address}"))

        elif isinstance(asm, CalldatasizePin):
            if seen_calldatasize:
                diags.append(_err("0036", "duplicate CalldatasizePin"))
            seen_calldatasize = True
            if not 0 <= asm.size <= _BV256_MAX:
                diags.append(_err("0037", f"CalldatasizePin.size out of bv256 range: {asm.size}"))

        elif isinstance(asm, CalldataBytePin):
            if not 0 <= asm.offset <= _BV256_MAX:
                diags.append(_err("0040", f"CalldataBytePin.offset out of range: {asm.offset}"))
            if not 0 <= asm.value <= 255:
                diags.append(_err("0041", f"CalldataBytePin.value not a byte (0..255): {asm.value}"))
            if asm.offset in seen_calldata_pins:
                prev = seen_calldata_pins[asm.offset]
                if prev != asm.value:
                    diags.append(_err(
                        "0042",
                        f"conflicting CalldataBytePin at offset {asm.offset}: "
                        f"{prev} vs {asm.value}",
                    ))
            else:
                seen_calldata_pins[asm.offset] = asm.value

        elif isinstance(asm, StoragePin):
            if asm.slot in seen_storage_pins:
                diags.append(_err("0050", f"duplicate StoragePin for slot {asm.slot}"))
            seen_storage_pins.add(asm.slot)
            if not 0 <= asm.slot <= _BV256_MAX:
                diags.append(_err("0051", f"StoragePin.slot out of bv256 range: {asm.slot}"))
            if not 0 <= asm.value <= _BV256_MAX:
                diags.append(_err("0052", f"StoragePin.value out of bv256 range: {asm.value}"))

        elif isinstance(asm, StorageWarm):
            if not 0 <= asm.slot <= _BV256_MAX:
                diags.append(_err("0055", f"StorageWarm.slot out of bv256 range: {asm.slot}"))

        elif isinstance(asm, GasLimitPin):
            if seen_gas:
                diags.append(_err("0060", "duplicate GasLimitPin"))
            seen_gas = True
            if not 0 <= asm.gas <= _BV64_MAX:
                diags.append(_err("0061", f"GasLimitPin.gas out of bv64 range: {asm.gas}"))

    # --- property ---
    prop = spec.property
    if not isinstance(prop, ReachProperty):
        diags.append(_err("0070", "property is not a ReachProperty"))
    else:
        if prop.kind == ReachKind.STORAGE_EQ:
            if prop.slot is None:
                diags.append(_err("0071", "ReachProperty(storage_eq) requires slot"))
            elif not 0 <= prop.slot <= _BV256_MAX:
                diags.append(_err("0072", f"ReachProperty.slot out of bv256 range: {prop.slot}"))
            if prop.value is None:
                diags.append(_err("0073", "ReachProperty(storage_eq) requires value"))
            elif not 0 <= prop.value <= _BV256_MAX:
                diags.append(_err("0074", f"ReachProperty.value out of bv256 range: {prop.value}"))

        elif prop.kind == ReachKind.RETURNDATA_EQ:
            if prop.offset is None:
                diags.append(_err("0075", "ReachProperty(returndata_eq) requires offset"))
            elif not 0 <= prop.offset <= _BV256_MAX:
                diags.append(_err("0076", f"ReachProperty.offset out of bv256 range: {prop.offset}"))
            if prop.data is None:
                diags.append(_err("0077", "ReachProperty(returndata_eq) requires data"))
            else:
                for j, b in enumerate(prop.data):
                    if not 0 <= b <= 255:
                        diags.append(_err("0078", f"ReachProperty.data[{j}] not a byte: {b}"))

        elif prop.kind in (ReachKind.REVERT, ReachKind.STOP):
            pass  # no extra fields required

    # --- analysis ---
    an = spec.analysis
    if an.engine not in _ALLOWED_ENGINES:
        diags.append(_err("0080", f"analysis.engine not supported: {an.engine!r}; allowed: {sorted(_ALLOWED_ENGINES)}"))
    if an.bound is not None and an.bound <= 0:
        diags.append(_err("0081", f"analysis.bound must be positive, got {an.bound}"))
    if an.timeout is not None and an.timeout <= 0:
        diags.append(_err("0082", f"analysis.timeout must be positive, got {an.timeout}"))

    return diags


__all__ = [
    "PAIR_ID",
    "SCHEMA_VERSION",
    "EvmVersion",
    "BytecodeRef",
    "AnalysisScope",
    "CallerPin",
    "CallvaluePin",
    "OriginPin",
    "CalldatasizePin",
    "CalldataBytePin",
    "StoragePin",
    "StorageWarm",
    "GasLimitPin",
    "ReachKind",
    "ReachProperty",
    "AnalysisDirective",
    "EvmBtor2Spec",
    "validate_evm_btor2_spec",
]
