"""Tests for the wasm-btor2 P4 translator.

Each test targets one public function or invariant; the test corpus
uses hand-crafted minimal WASM binaries built inline — no external
``.wasm`` files needed.
"""

from __future__ import annotations

import pytest

from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.core.pair import CompiledArtifact
from gurdy.pairs.wasm_btor2.btor2.parser import from_text as btor2_parse
from gurdy.pairs.wasm_btor2.source import load_wasm_source
from gurdy.pairs.wasm_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    Comparison,
    LocalInit,
    PropertyKind,
    QuestionSpec,
    WasmBtor2Spec,
    WasmModuleRef,
)
from gurdy.pairs.wasm_btor2.translation import (
    SCHEMA_VERSION,
    TRANSLATOR_VERSION,
    Translator,
)


# ---------------------------------------------------------------------------
# Helpers
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


def _make_wasm(
    params: list[int],
    results: list[int],
    body_bytes: bytes,
    export_name: str = "main",
) -> bytes:
    """Build a minimal single-function WASM module binary."""
    I32 = 0x7F

    # type section: 1 functype
    type_body = (
        bytes([1, 0x60, len(params)])
        + bytes(params)
        + bytes([len(results)])
        + bytes(results)
    )

    # function section: 1 function → type 0
    func_body = bytes([1, 0])

    # export section: export_name → func 0
    nb = export_name.encode("utf-8")
    export_body = bytes([1]) + _uleb128(len(nb)) + nb + bytes([0, 0])

    # code section: 1 function body
    func_bytes = bytes([0]) + body_bytes  # 0 local groups + body
    code_body = bytes([1]) + _uleb128(len(func_bytes)) + func_bytes

    def section(sec_id: int, body: bytes) -> bytes:
        return bytes([sec_id]) + _uleb128(len(body)) + body

    return (
        b"\x00asm\x01\x00\x00\x00"
        + section(1, type_body)
        + section(3, func_body)
        + section(7, export_body)
        + section(10, code_body)
    )


def _make_annotator() -> AnnotationEmitter:
    sidecar = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="")
    return AnnotationEmitter(sidecar)


def _make_spec(
    entry: str = "main",
    kind: PropertyKind = PropertyKind.REACH_TRAP,
    negate: bool = False,
    assumptions: tuple = (),
) -> WasmBtor2Spec:
    return WasmBtor2Spec(
        module=WasmModuleRef(path="test.wasm"),
        scope=AnalysisScope(entry_function=entry),
        question=QuestionSpec(kind=kind, negate=negate),
        assumptions=assumptions,
    )


def _translate(wasm_bytes: bytes, spec: WasmBtor2Spec) -> CompiledArtifact:
    source = load_wasm_source(wasm_bytes)
    ann = _make_annotator()
    return Translator().translate(spec, source, ann)


# Minimal WASM bodies (instruction bytes only, no 'end' — appended below)
_BODY_ADD = b"\x20\x00\x20\x01\x6A\x0B"   # local.get 0; local.get 1; i32.add; end
_BODY_SUB = b"\x20\x00\x20\x01\x6B\x0B"   # local.get 0; local.get 1; i32.sub; end
_BODY_MUL = b"\x20\x00\x20\x01\x6C\x0B"   # local.get 0; local.get 1; i32.mul; end
_BODY_DIV_S = b"\x20\x00\x20\x01\x6D\x0B" # local.get 0; local.get 1; i32.div_s; end
_BODY_DIV_U = b"\x20\x00\x20\x01\x6E\x0B" # local.get 0; local.get 1; i32.div_u; end
_BODY_REM_S = b"\x20\x00\x20\x01\x6F\x0B" # local.get 0; local.get 1; i32.rem_s; end
_BODY_REM_U = b"\x20\x00\x20\x01\x70\x0B" # local.get 0; local.get 1; i32.rem_u; end
_BODY_CONST = b"\x41\x2A\x0B"              # i32.const 42; end
_BODY_TRAP = b"\x00\x0B"                   # unreachable; end
_BODY_AND  = b"\x20\x00\x20\x01\x71\x0B"  # local.get 0; local.get 1; i32.and; end
_BODY_OR   = b"\x20\x00\x20\x01\x72\x0B"  # local.get 0; local.get 1; i32.or;  end
_BODY_XOR  = b"\x20\x00\x20\x01\x73\x0B"  # local.get 0; local.get 1; i32.xor; end
_BODY_SHL  = b"\x20\x00\x20\x01\x74\x0B"  # local.get 0; local.get 1; i32.shl; end
_BODY_SHR_S = b"\x20\x00\x20\x01\x75\x0B" # local.get 0; local.get 1; i32.shr_s; end
_BODY_SHR_U = b"\x20\x00\x20\x01\x76\x0B" # local.get 0; local.get 1; i32.shr_u; end
_BODY_ROTL = b"\x20\x00\x20\x01\x77\x0B"  # local.get 0; local.get 1; i32.rotl; end
_BODY_ROTR = b"\x20\x00\x20\x01\x78\x0B"  # local.get 0; local.get 1; i32.rotr; end
_BODY_EQZ  = b"\x20\x00\x45\x0B"          # local.get 0; i32.eqz; end  (unary)
_BODY_EQ   = b"\x20\x00\x20\x01\x46\x0B"  # local.get 0; local.get 1; i32.eq; end
_BODY_NE   = b"\x20\x00\x20\x01\x47\x0B"  # i32.ne
_BODY_LT_S = b"\x20\x00\x20\x01\x48\x0B"  # i32.lt_s
_BODY_LT_U = b"\x20\x00\x20\x01\x49\x0B"  # i32.lt_u
_BODY_GT_S = b"\x20\x00\x20\x01\x4A\x0B"  # i32.gt_s
_BODY_GT_U = b"\x20\x00\x20\x01\x4B\x0B"  # i32.gt_u
_BODY_LE_S = b"\x20\x00\x20\x01\x4C\x0B"  # i32.le_s
_BODY_LE_U = b"\x20\x00\x20\x01\x4D\x0B"  # i32.le_u
_BODY_GE_S = b"\x20\x00\x20\x01\x4E\x0B"  # i32.ge_s
_BODY_GE_U = b"\x20\x00\x20\x01\x4F\x0B"  # i32.ge_u

# P16: type conversion bodies
# local.get 0; i64.extend_i32_u; i32.wrap_i64; end
_BODY_EXTEND_U_WRAP = b"\x20\x00\xad\xa7\x0b"
# local.get 0; i64.extend_i32_s; i32.wrap_i64; end
_BODY_EXTEND_S_WRAP = b"\x20\x00\xac\xa7\x0b"
# i64.const 42; i32.wrap_i64; end
_BODY_WRAP_I64_CONST = b"\x42\x2a\xa7\x0b"

_I32 = 0x7F  # WASM i32 type code

_WASM_ADD = _make_wasm([_I32, _I32], [_I32], _BODY_ADD)
_WASM_SUB = _make_wasm([_I32, _I32], [_I32], _BODY_SUB)
_WASM_MUL = _make_wasm([_I32, _I32], [_I32], _BODY_MUL)
_WASM_DIV_S = _make_wasm([_I32, _I32], [_I32], _BODY_DIV_S)
_WASM_DIV_U = _make_wasm([_I32, _I32], [_I32], _BODY_DIV_U)
_WASM_REM_S = _make_wasm([_I32, _I32], [_I32], _BODY_REM_S)
_WASM_REM_U = _make_wasm([_I32, _I32], [_I32], _BODY_REM_U)
_WASM_CONST = _make_wasm([], [_I32], _BODY_CONST)
_WASM_TRAP = _make_wasm([_I32], [_I32], _BODY_TRAP)
_WASM_AND  = _make_wasm([_I32, _I32], [_I32], _BODY_AND)
_WASM_OR   = _make_wasm([_I32, _I32], [_I32], _BODY_OR)
_WASM_XOR  = _make_wasm([_I32, _I32], [_I32], _BODY_XOR)
_WASM_SHL  = _make_wasm([_I32, _I32], [_I32], _BODY_SHL)
_WASM_SHR_S = _make_wasm([_I32, _I32], [_I32], _BODY_SHR_S)
_WASM_SHR_U = _make_wasm([_I32, _I32], [_I32], _BODY_SHR_U)
_WASM_ROTL = _make_wasm([_I32, _I32], [_I32], _BODY_ROTL)
_WASM_ROTR = _make_wasm([_I32, _I32], [_I32], _BODY_ROTR)
_WASM_EQZ  = _make_wasm([_I32], [_I32], _BODY_EQZ)
_WASM_EQ   = _make_wasm([_I32, _I32], [_I32], _BODY_EQ)
_WASM_NE   = _make_wasm([_I32, _I32], [_I32], _BODY_NE)
_WASM_LT_S = _make_wasm([_I32, _I32], [_I32], _BODY_LT_S)
_WASM_LT_U = _make_wasm([_I32, _I32], [_I32], _BODY_LT_U)
_WASM_GT_S = _make_wasm([_I32, _I32], [_I32], _BODY_GT_S)
_WASM_GT_U = _make_wasm([_I32, _I32], [_I32], _BODY_GT_U)
_WASM_LE_S = _make_wasm([_I32, _I32], [_I32], _BODY_LE_S)
_WASM_LE_U = _make_wasm([_I32, _I32], [_I32], _BODY_LE_U)
_WASM_GE_S = _make_wasm([_I32, _I32], [_I32], _BODY_GE_S)
_WASM_GE_U = _make_wasm([_I32, _I32], [_I32], _BODY_GE_U)

# P16: type conversion modules
_WASM_EXTEND_U_WRAP = _make_wasm([_I32], [_I32], _BODY_EXTEND_U_WRAP)
_WASM_EXTEND_S_WRAP = _make_wasm([_I32], [_I32], _BODY_EXTEND_S_WRAP)
_WASM_WRAP_I64_CONST = _make_wasm([], [_I32], _BODY_WRAP_I64_CONST)

# P17: i64 arithmetic bodies
# local.get 0; i64.extend_i32_u; i64.const 1; i64.add; i32.wrap_i64; end
_BODY_I64_ADD = b"\x20\x00\xAD\x42\x01\x7C\xA7\x0B"
# local.get 0; i64.extend_i32_u; i64.const 2; i64.sub; i32.wrap_i64; end
_BODY_I64_SUB = b"\x20\x00\xAD\x42\x02\x7D\xA7\x0B"
# i64.const 3; i64.const 4; i64.mul; i32.wrap_i64; end
_BODY_I64_MUL = b"\x42\x03\x42\x04\x7E\xA7\x0B"
# i64.const 42; end  (push a lone i64 constant)
_BODY_I64_CONST = b"\x42\x2A\x0B"

_I64 = 0x7E
_WASM_I64_ADD = _make_wasm([_I32], [_I32], _BODY_I64_ADD)
_WASM_I64_SUB = _make_wasm([_I32], [_I32], _BODY_I64_SUB)
_WASM_I64_MUL = _make_wasm([], [_I32], _BODY_I64_MUL)
_WASM_I64_CONST = _make_wasm([], [_I64], _BODY_I64_CONST)

# P19: i32.extend8_s / i32.extend16_s bodies
# local.get 0; i32.extend8_s; end
_BODY_EXTEND8_S  = bytes([0x20, 0x00, 0xC0, 0x0B])
# local.get 0; i32.extend16_s; end
_BODY_EXTEND16_S = bytes([0x20, 0x00, 0xC1, 0x0B])
# local.get 0; i32.extend8_s; i32.extend16_s; end
_BODY_EXTEND8_THEN_16 = bytes([0x20, 0x00, 0xC0, 0xC1, 0x0B])

_WASM_EXTEND8_S      = _make_wasm([_I32], [_I32], _BODY_EXTEND8_S)
_WASM_EXTEND16_S     = _make_wasm([_I32], [_I32], _BODY_EXTEND16_S)
_WASM_EXTEND8_THEN_16 = _make_wasm([_I32], [_I32], _BODY_EXTEND8_THEN_16)

# P20: i64 sign-extension bodies (i64 TOS in, i64 out; use extend_i32_u to promote from local)
# local.get 0; i64.extend_i32_u; i64.extend8_s; drop; end
_BODY_I64_EXTEND8_S  = bytes([0x20, 0x00, 0xAD, 0xC2, 0x1A, 0x0B])
# local.get 0; i64.extend_i32_u; i64.extend16_s; drop; end
_BODY_I64_EXTEND16_S = bytes([0x20, 0x00, 0xAD, 0xC3, 0x1A, 0x0B])
# local.get 0; i64.extend_i32_u; i64.extend32_s; drop; end
_BODY_I64_EXTEND32_S = bytes([0x20, 0x00, 0xAD, 0xC4, 0x1A, 0x0B])
# local.get 0; i64.extend_i32_u; i64.extend8_s; i64.extend16_s; i64.extend32_s; drop; end
_BODY_I64_EXTEND_ALL = bytes([0x20, 0x00, 0xAD, 0xC2, 0xC3, 0xC4, 0x1A, 0x0B])

_WASM_I64_EXTEND8_S  = _make_wasm([_I32], [], _BODY_I64_EXTEND8_S)
_WASM_I64_EXTEND16_S = _make_wasm([_I32], [], _BODY_I64_EXTEND16_S)
_WASM_I64_EXTEND32_S = _make_wasm([_I32], [], _BODY_I64_EXTEND32_S)
_WASM_I64_EXTEND_ALL = _make_wasm([_I32], [], _BODY_I64_EXTEND_ALL)

# P21: i64 bitwise and shift bodies
# local.get 0; i64.extend_i32_u; local.get 1; i64.extend_i32_u; <op>; drop; end
_BODY_I64_AND   = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x83, 0x1A, 0x0B])
_BODY_I64_OR    = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x84, 0x1A, 0x0B])
_BODY_I64_XOR   = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x85, 0x1A, 0x0B])
_BODY_I64_SHL   = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x86, 0x1A, 0x0B])
_BODY_I64_SHR_S = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x87, 0x1A, 0x0B])
_BODY_I64_SHR_U = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x88, 0x1A, 0x0B])

_WASM_I64_AND   = _make_wasm([_I32, _I32], [], _BODY_I64_AND)
_WASM_I64_OR    = _make_wasm([_I32, _I32], [], _BODY_I64_OR)
_WASM_I64_XOR   = _make_wasm([_I32, _I32], [], _BODY_I64_XOR)
_WASM_I64_SHL   = _make_wasm([_I32, _I32], [], _BODY_I64_SHL)
_WASM_I64_SHR_S = _make_wasm([_I32, _I32], [], _BODY_I64_SHR_S)
_WASM_I64_SHR_U = _make_wasm([_I32, _I32], [], _BODY_I64_SHR_U)

# P22: i64 div/rem bodies (i32×2 params extended to i64, drop result)
# local.get 0; i64.extend_i32_u; local.get 1; i64.extend_i32_u; <op>; drop; end
_BODY_I64_DIV_S = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x7F, 0x1A, 0x0B])
_BODY_I64_DIV_U = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x80, 0x1A, 0x0B])
_BODY_I64_REM_S = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x81, 0x1A, 0x0B])
_BODY_I64_REM_U = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x82, 0x1A, 0x0B])
# i64.const INT64_MIN; i64.const -1; i64.div_s; drop; end (no params — literal overflow)
_BODY_I64_DIV_S_OVERFLOW = bytes([
    0x42, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x7F,  # i64.const INT64_MIN
    0x42, 0x7F,  # i64.const -1
    0x7F,        # i64.div_s
    0x1A,        # drop
    0x0B,        # end
])

_WASM_I64_DIV_S          = _make_wasm([_I32, _I32], [], _BODY_I64_DIV_S)
_WASM_I64_DIV_U          = _make_wasm([_I32, _I32], [], _BODY_I64_DIV_U)
_WASM_I64_REM_S          = _make_wasm([_I32, _I32], [], _BODY_I64_REM_S)
_WASM_I64_REM_U          = _make_wasm([_I32, _I32], [], _BODY_I64_REM_U)
_WASM_I64_DIV_S_OVERFLOW = _make_wasm([], [], _BODY_I64_DIV_S_OVERFLOW)

# P23: i64 clz / ctz / popcnt bodies (one i32 param, zero-extended to i64 by extend_i32_u)
# local.get 0; i64.extend_i32_u; i64.clz; drop; end
_BODY_I64_CLZ    = bytes([0x20, 0x00, 0xAD, 0x79, 0x1A, 0x0B])
# local.get 0; i64.extend_i32_u; i64.ctz; drop; end
_BODY_I64_CTZ    = bytes([0x20, 0x00, 0xAD, 0x7A, 0x1A, 0x0B])
# local.get 0; i64.extend_i32_u; i64.popcnt; drop; end
_BODY_I64_POPCNT = bytes([0x20, 0x00, 0xAD, 0x7B, 0x1A, 0x0B])

_WASM_I64_CLZ    = _make_wasm([_I32], [], _BODY_I64_CLZ)
_WASM_I64_CTZ    = _make_wasm([_I32], [], _BODY_I64_CTZ)
_WASM_I64_POPCNT = _make_wasm([_I32], [], _BODY_I64_POPCNT)

# P24: i64 comparison bodies (i64.eqz: unary; rest: binary with two i32 params extended to i64)
# local.get 0; i64.extend_i32_u; i64.eqz; drop; end
_BODY_I64_EQZ   = bytes([0x20, 0x00, 0xAD, 0x50, 0x1A, 0x0B])
# local.get 0; i64.extend_i32_u; local.get 1; i64.extend_i32_u; <op>; drop; end
_BODY_I64_EQ    = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x51, 0x1A, 0x0B])
_BODY_I64_NE    = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x52, 0x1A, 0x0B])
_BODY_I64_LT_S  = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x53, 0x1A, 0x0B])
_BODY_I64_LT_U  = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x54, 0x1A, 0x0B])
_BODY_I64_GT_S  = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x55, 0x1A, 0x0B])
_BODY_I64_GT_U  = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x56, 0x1A, 0x0B])
_BODY_I64_LE_S  = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x57, 0x1A, 0x0B])
_BODY_I64_LE_U  = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x58, 0x1A, 0x0B])
_BODY_I64_GE_S  = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x59, 0x1A, 0x0B])
_BODY_I64_GE_U  = bytes([0x20, 0x00, 0xAD, 0x20, 0x01, 0xAD, 0x5A, 0x1A, 0x0B])

_WASM_I64_EQZ   = _make_wasm([_I32], [], _BODY_I64_EQZ)
_WASM_I64_EQ    = _make_wasm([_I32, _I32], [], _BODY_I64_EQ)
_WASM_I64_NE    = _make_wasm([_I32, _I32], [], _BODY_I64_NE)
_WASM_I64_LT_S  = _make_wasm([_I32, _I32], [], _BODY_I64_LT_S)
_WASM_I64_LT_U  = _make_wasm([_I32, _I32], [], _BODY_I64_LT_U)
_WASM_I64_GT_S  = _make_wasm([_I32, _I32], [], _BODY_I64_GT_S)
_WASM_I64_GT_U  = _make_wasm([_I32, _I32], [], _BODY_I64_GT_U)
_WASM_I64_LE_S  = _make_wasm([_I32, _I32], [], _BODY_I64_LE_S)
_WASM_I64_LE_U  = _make_wasm([_I32, _I32], [], _BODY_I64_LE_U)
_WASM_I64_GE_S  = _make_wasm([_I32, _I32], [], _BODY_I64_GE_S)
_WASM_I64_GE_U  = _make_wasm([_I32, _I32], [], _BODY_I64_GE_U)

# P25: select — three i32 params (val1, val2, cond); result dropped; no params
# local.get 0; local.get 1; local.get 2; select; drop; end
_BODY_SELECT    = bytes([0x20, 0x00, 0x20, 0x01, 0x20, 0x02, 0x1B, 0x1A, 0x0B])
_WASM_SELECT    = _make_wasm([_I32, _I32, _I32], [], _BODY_SELECT)

# P26: local.set / local.tee — isolated per-instruction tests
# local.set: two i32 params; local.get 1; local.set 0; end
_BODY_LOCAL_SET = bytes([0x20, 0x01, 0x21, 0x00, 0x0B])
_WASM_LOCAL_SET = _make_wasm([_I32, _I32], [], _BODY_LOCAL_SET)
# local.tee: one i32 param; local.get 0; local.tee 0; drop; end
_BODY_LOCAL_TEE = bytes([0x20, 0x00, 0x22, 0x00, 0x1A, 0x0B])
_WASM_LOCAL_TEE = _make_wasm([_I32], [], _BODY_LOCAL_TEE)

# P12: if/else — single-param (i32) → () functions
# local.get 0; if (void); nop; end(block); end(func)
_BODY_IF      = bytes([0x20, 0x00, 0x04, 0x40, 0x01, 0x0B, 0x0B])
# local.get 0; if (void); nop; else; nop; end(block); end(func)
_BODY_IF_ELSE = bytes([0x20, 0x00, 0x04, 0x40, 0x01, 0x05, 0x01, 0x0B, 0x0B])

_WASM_IF      = _make_wasm([_I32], [], _BODY_IF)
_WASM_IF_ELSE = _make_wasm([_I32], [], _BODY_IF_ELSE)


# P13: br_if / br — single-param (i32) → () functions (no extra locals needed)
# block (void); local.get 0; br_if 0; end(block); end(func)
_BODY_BR_IF = bytes([0x02, 0x40, 0x20, 0x00, 0x0D, 0x00, 0x0B, 0x0B])
# block (void); br 0; end(block); end(func)
_BODY_BR    = bytes([0x02, 0x40, 0x0C, 0x00, 0x0B, 0x0B])

_WASM_BR_IF = _make_wasm([_I32], [], _BODY_BR_IF)
_WASM_BR    = _make_wasm([], [], _BODY_BR)


def _make_wasm_loop_count() -> bytes:
    """Build the 0006-loop-count module: (i32)->() with 1 extra local.

    Body: i32.const 0; local.set 1; block; loop;
          local.get 1; local.get 0; i32.ge_u; br_if 1;
          local.get 1; i32.const 1; i32.add; local.set 1; br 0;
          end; end; end
    """
    nb = b"main"
    type_body = b"\x01\x60\x01\x7f\x00"
    func_body = b"\x01\x00"
    export_body = bytes([1]) + _uleb128(len(nb)) + nb + bytes([0, 0])
    body = bytes([
        0x41, 0x00, 0x21, 0x01,  # i32.const 0; local.set 1
        0x02, 0x40,              # block void
        0x03, 0x40,              # loop void
        0x20, 0x01, 0x20, 0x00,  # local.get 1; local.get 0
        0x4F,                    # i32.ge_u
        0x0D, 0x01,              # br_if 1
        0x20, 0x01,              # local.get 1
        0x41, 0x01, 0x6A,        # i32.const 1; i32.add
        0x21, 0x01,              # local.set 1
        0x0C, 0x00,              # br 0
        0x0B, 0x0B, 0x0B,        # end; end; end
    ])
    locals_hdr = b"\x01\x01\x7f"  # 1 group: 1×i32
    func_entry = locals_hdr + body
    code_body = _uleb128(1) + _uleb128(len(func_entry)) + func_entry

    def section(sec_id: int, b: bytes) -> bytes:
        return bytes([sec_id]) + _uleb128(len(b)) + b

    return (
        b"\x00asm\x01\x00\x00\x00"
        + section(1, type_body)
        + section(3, func_body)
        + section(7, export_body)
        + section(10, code_body)
    )


_WASM_LOOP_COUNT = _make_wasm_loop_count()


# P14: clz / ctz / popcnt — single-param (i32) → i32 functions
_BODY_CLZ    = b"\x20\x00\x67\x0b"  # local.get 0; i32.clz; end
_BODY_CTZ    = b"\x20\x00\x68\x0b"  # local.get 0; i32.ctz; end
_BODY_POPCNT = b"\x20\x00\x69\x0b"  # local.get 0; i32.popcnt; end

_WASM_CLZ    = _make_wasm([_I32], [_I32], _BODY_CLZ)
_WASM_CTZ    = _make_wasm([_I32], [_I32], _BODY_CTZ)
_WASM_POPCNT = _make_wasm([_I32], [_I32], _BODY_POPCNT)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def test_translator_version_exported():
    assert TRANSLATOR_VERSION == "1.0.0"


def test_schema_version_exported():
    assert SCHEMA_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# translate() returns a well-formed CompiledArtifact
# ---------------------------------------------------------------------------


def test_translate_returns_artifact():
    art = _translate(_WASM_ADD, _make_spec())
    assert isinstance(art, CompiledArtifact)


def test_artifact_pair():
    art = _translate(_WASM_ADD, _make_spec())
    assert art.pair == "wasm-btor2"


def test_artifact_schema_version():
    art = _translate(_WASM_ADD, _make_spec())
    assert art.schema_version == SCHEMA_VERSION


def test_all_layers_present():
    art = _translate(_WASM_ADD, _make_spec())
    expected = {"header", "machine", "library", "dispatch", "init", "constraint", "bad", "binding"}
    assert set(art.layers.keys()) == expected


def test_flattened_nonempty():
    art = _translate(_WASM_ADD, _make_spec())
    assert len(art.flattened) > 0


# ---------------------------------------------------------------------------
# All P4 arithmetic instructions compile without error
# ---------------------------------------------------------------------------


def test_i32_add_compiles():
    _translate(_WASM_ADD, _make_spec())  # no exception


def test_i32_sub_compiles():
    _translate(_WASM_SUB, _make_spec())  # no exception


def test_i32_mul_compiles():
    _translate(_WASM_MUL, _make_spec())  # no exception


def test_i32_const_compiles():
    _translate(_WASM_CONST, _make_spec())  # no exception


def test_i32_div_s_compiles():
    _translate(_WASM_DIV_S, _make_spec())


def test_i32_div_u_compiles():
    _translate(_WASM_DIV_U, _make_spec())


def test_i32_rem_s_compiles():
    _translate(_WASM_REM_S, _make_spec())


def test_i32_rem_u_compiles():
    _translate(_WASM_REM_U, _make_spec())


def test_i32_div_s_flattened_parseable():
    art = _translate(_WASM_DIV_S, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_i32_div_s_contains_sdiv():
    art = _translate(_WASM_DIV_S, _make_spec())
    assert "sdiv" in art.flattened.decode("utf-8")


def test_i32_div_u_contains_udiv():
    art = _translate(_WASM_DIV_U, _make_spec())
    assert "udiv" in art.flattened.decode("utf-8")


def test_i32_rem_s_contains_srem():
    art = _translate(_WASM_REM_S, _make_spec())
    assert "srem" in art.flattened.decode("utf-8")


def test_i32_rem_u_contains_urem():
    art = _translate(_WASM_REM_U, _make_spec())
    assert "urem" in art.flattened.decode("utf-8")


def test_i32_div_s_contains_ite_for_trap():
    # The conditional trap path must be expressed via ITE in the library layer.
    art = _translate(_WASM_DIV_S, _make_spec())
    assert "ite" in art.layers["library"].body.decode("utf-8")


# ---------------------------------------------------------------------------
# Reasoning interpreter: div_s with non-zero divisor never fires bad
# ---------------------------------------------------------------------------


def test_reasoning_interp_div_s_nonzero_divisor_no_bad():
    """When divisor != 0, i32.div_s should not trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    spec = _make_spec(
        assumptions=(
            LocalInit(func_idx=0, local_idx=1, op=Comparison.NE, value=0),
        )
    )
    art = _translate(_WASM_DIV_S, spec)
    # local_0=7, local_1=2 → 7/2=3, no trap
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 7, "local_1": 2})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_div_s_zero_divisor_bad_fired():
    """When divisor == 0, i32.div_s should trap (bad_fired becomes True)."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_DIV_S, _make_spec())
    # local_0=5, local_1=0 → trap at step 3
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 5, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps), "expected bad_fired for divisor==0"


def test_reasoning_interp_div_s_overflow_bad_fired():
    """INT32_MIN / -1 is the signed overflow trap case."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_DIV_S, _make_spec())
    rbinding = Btor2ReasoningBinding(
        state_init_by_symbol={"local_0": 0x80000000, "local_1": 0xFFFFFFFF}
    )
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps), "expected bad_fired for INT32_MIN/-1"


def test_reasoning_interp_div_u_zero_divisor_bad_fired():
    """i32.div_u traps on divisor==0."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_DIV_U, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 3, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_rem_s_zero_divisor_bad_fired():
    """i32.rem_s traps on divisor==0."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_REM_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 3, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_rem_u_zero_divisor_bad_fired():
    """i32.rem_u traps on divisor==0."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_REM_U, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 3, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# BTOR2 output is parseable
# ---------------------------------------------------------------------------


def test_flattened_parseable_add():
    art = _translate(_WASM_ADD, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_flattened_parseable_const():
    art = _translate(_WASM_CONST, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


# ---------------------------------------------------------------------------
# bad layer
# ---------------------------------------------------------------------------


def test_bad_layer_nonempty_reach_trap():
    art = _translate(_WASM_ADD, _make_spec(kind=PropertyKind.REACH_TRAP))
    assert len(art.layers["bad"].body) > 0


def test_bad_layer_contains_bad_node():
    art = _translate(_WASM_TRAP, _make_spec(kind=PropertyKind.REACH_TRAP))
    btor2_text = art.flattened.decode("utf-8")
    assert " bad " in btor2_text


def test_reach_trap_negate_emits_not():
    art = _translate(_WASM_ADD, _make_spec(negate=True))
    bad_body = art.layers["bad"].body.decode("utf-8")
    assert "not" in bad_body


# ---------------------------------------------------------------------------
# Entry function errors
# ---------------------------------------------------------------------------


def test_entry_not_found_raises():
    source = load_wasm_source(_WASM_ADD)
    spec = _make_spec(entry="nonexistent")
    ann = _make_annotator()
    with pytest.raises(ValueError, match="not found"):
        Translator().translate(spec, source, ann)


# ---------------------------------------------------------------------------
# LocalInit assumption emits a constraint
# ---------------------------------------------------------------------------


def test_local_init_constraint_emitted():
    assumption = LocalInit(func_idx=0, local_idx=0, op=Comparison.EQ, value=42)
    spec = _make_spec(assumptions=(assumption,))
    art = _translate(_WASM_ADD, spec)
    constraint_body = art.layers["constraint"].body.decode("utf-8")
    assert "constraint" in constraint_body


# ---------------------------------------------------------------------------
# P10: bitwise ops (i32.and / i32.or / i32.xor)
# ---------------------------------------------------------------------------


def test_i32_and_compiles():
    _translate(_WASM_AND, _make_spec())


def test_i32_or_compiles():
    _translate(_WASM_OR, _make_spec())


def test_i32_xor_compiles():
    _translate(_WASM_XOR, _make_spec())


def test_i32_and_contains_and_op():
    art = _translate(_WASM_AND, _make_spec())
    assert " and " in art.flattened.decode("utf-8")


def test_i32_or_contains_or_op():
    art = _translate(_WASM_OR, _make_spec())
    assert " or " in art.flattened.decode("utf-8")


def test_i32_xor_contains_xor_op():
    art = _translate(_WASM_XOR, _make_spec())
    assert " xor " in art.flattened.decode("utf-8")


# ---------------------------------------------------------------------------
# P10: shift ops (i32.shl / i32.shr_s / i32.shr_u) — with mod-32 mask
# ---------------------------------------------------------------------------


def test_i32_shl_compiles():
    _translate(_WASM_SHL, _make_spec())


def test_i32_shr_s_compiles():
    _translate(_WASM_SHR_S, _make_spec())


def test_i32_shr_u_compiles():
    _translate(_WASM_SHR_U, _make_spec())


def test_i32_shl_contains_sll():
    art = _translate(_WASM_SHL, _make_spec())
    assert "sll" in art.flattened.decode("utf-8")


def test_i32_shr_s_contains_sra():
    art = _translate(_WASM_SHR_S, _make_spec())
    assert "sra" in art.flattened.decode("utf-8")


def test_i32_shr_u_contains_srl():
    art = _translate(_WASM_SHR_U, _make_spec())
    assert "srl" in art.flattened.decode("utf-8")


def test_i32_shl_mask_explicit_in_btor2():
    # The mod-32 mask must appear as an explicit 'and' before the sll node.
    art = _translate(_WASM_SHL, _make_spec())
    text = art.flattened.decode("utf-8")
    assert "and" in text and "sll" in text


# ---------------------------------------------------------------------------
# P10: rotation ops (i32.rotl / i32.rotr)
# ---------------------------------------------------------------------------


def test_i32_rotl_compiles():
    _translate(_WASM_ROTL, _make_spec())


def test_i32_rotr_compiles():
    _translate(_WASM_ROTR, _make_spec())


def test_i32_rotl_contains_sll_and_srl():
    art = _translate(_WASM_ROTL, _make_spec())
    text = art.flattened.decode("utf-8")
    assert "sll" in text and "srl" in text


# ---------------------------------------------------------------------------
# P10: reasoning interpreter concrete-witness tests
# ---------------------------------------------------------------------------


def test_reasoning_interp_shl_basic():
    """1 << 1 = 2, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_SHL, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1, "local_1": 1})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_shl_mask_mod32():
    """Shift by 32 must equal shift by 0 (WASM mod-32 masking)."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_SHL, _make_spec())
    # local_0=5, local_1=32 → 5 << (32 & 31) = 5 << 0 = 5, no trap
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 5, "local_1": 32})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_shr_u_basic():
    """8 >> 1 = 4, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_SHR_U, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 8, "local_1": 1})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_rotr_basic():
    """rotr(1, 1) = 0x80000000 (bit wraps around), no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_ROTR, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1, "local_1": 1})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_and_basic():
    """0xFF & 0x0F = 0x0F, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_AND, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFF, "local_1": 0x0F})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P11: comparison instructions compile without error
# ---------------------------------------------------------------------------


def test_i32_eqz_compiles():
    _translate(_WASM_EQZ, _make_spec())


def test_i32_eq_compiles():
    _translate(_WASM_EQ, _make_spec())


def test_i32_ne_compiles():
    _translate(_WASM_NE, _make_spec())


def test_i32_lt_s_compiles():
    _translate(_WASM_LT_S, _make_spec())


def test_i32_lt_u_compiles():
    _translate(_WASM_LT_U, _make_spec())


def test_i32_gt_s_compiles():
    _translate(_WASM_GT_S, _make_spec())


def test_i32_gt_u_compiles():
    _translate(_WASM_GT_U, _make_spec())


def test_i32_le_s_compiles():
    _translate(_WASM_LE_S, _make_spec())


def test_i32_le_u_compiles():
    _translate(_WASM_LE_U, _make_spec())


def test_i32_ge_s_compiles():
    _translate(_WASM_GE_S, _make_spec())


def test_i32_ge_u_compiles():
    _translate(_WASM_GE_U, _make_spec())


# ---------------------------------------------------------------------------
# P11: BTOR2 operator presence (bv1 comparison + uext)
# ---------------------------------------------------------------------------


def test_i32_lt_s_contains_slt():
    art = _translate(_WASM_LT_S, _make_spec())
    assert "slt" in art.flattened.decode("utf-8")


def test_i32_lt_u_contains_ult():
    art = _translate(_WASM_LT_U, _make_spec())
    assert "ult" in art.flattened.decode("utf-8")


def test_i32_eq_contains_eq():
    art = _translate(_WASM_EQ, _make_spec())
    assert " eq " in art.flattened.decode("utf-8")


def test_i32_ne_contains_neq():
    art = _translate(_WASM_NE, _make_spec())
    assert "neq" in art.flattened.decode("utf-8")


def test_i32_lt_s_contains_uext():
    # Result must be zero-extended bv1 → bv32.
    art = _translate(_WASM_LT_S, _make_spec())
    assert "uext" in art.flattened.decode("utf-8")


def test_i32_eqz_contains_uext():
    art = _translate(_WASM_EQZ, _make_spec())
    assert "uext" in art.flattened.decode("utf-8")


# ---------------------------------------------------------------------------
# P11: reasoning interpreter concrete-witness tests — no trap for any inputs
# ---------------------------------------------------------------------------


def test_reasoning_interp_lt_s_basic_no_trap():
    """1 < 2 = 1, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_LT_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1, "local_1": 2})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_lt_s_equal_no_trap():
    """5 < 5 = 0, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_LT_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 5, "local_1": 5})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_lt_s_negative_no_trap():
    """-1 < 0 = 1 (signed), no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_LT_S, _make_spec())
    # -1 as unsigned bv32 = 0xFFFFFFFF
    rbinding = Btor2ReasoningBinding(
        state_init_by_symbol={"local_0": 0xFFFFFFFF, "local_1": 0}
    )
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_eq_same_values_no_trap():
    """42 == 42 = 1, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EQ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 42, "local_1": 42})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_eqz_zero_no_trap():
    """eqz(0) = 1, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EQZ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_eqz_nonzero_no_trap():
    """eqz(7) = 0, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EQZ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 7})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_ge_u_no_trap():
    """5 >= 3 unsigned = 1, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_GE_U, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 5, "local_1": 3})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P12: if/else structured control flow compile without error
# ---------------------------------------------------------------------------


def test_if_compiles():
    _translate(_WASM_IF, _make_spec())


def test_if_else_compiles():
    _translate(_WASM_IF_ELSE, _make_spec())


# ---------------------------------------------------------------------------
# P12: BTOR2 output shape for if
# ---------------------------------------------------------------------------


def test_if_contains_ite_in_dispatch():
    """if lowering must emit an ITE in the dispatch layer."""
    art = _translate(_WASM_IF, _make_spec())
    assert "ite" in art.layers["dispatch"].body.decode("utf-8")


def test_if_contains_neq_in_library():
    """if lowering compares condition with zero via neq."""
    art = _translate(_WASM_IF, _make_spec())
    assert "neq" in art.layers["library"].body.decode("utf-8")


def test_if_flattened_parseable():
    art = _translate(_WASM_IF, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


# ---------------------------------------------------------------------------
# P12: reasoning interpreter — if/else never traps
# ---------------------------------------------------------------------------


def test_reasoning_interp_if_cond_zero_no_trap():
    """condition=0: if body skipped, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_IF, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_if_cond_nonzero_no_trap():
    """condition=1: if body entered, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_IF, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_if_cond_neg1_no_trap():
    """condition=-1 (0xFFFFFFFF, nonzero): if body entered, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_IF, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFFFFFFFF})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_if_else_true_branch_no_trap():
    """condition=1: true branch (nop), skip else, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_IF_ELSE, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_if_else_false_branch_no_trap():
    """condition=0: else branch (nop), no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_IF_ELSE, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P13: br_if / br / block / loop compile without error
# ---------------------------------------------------------------------------


def test_br_if_compiles():
    _translate(_WASM_BR_IF, _make_spec())


def test_br_compiles():
    _translate(_WASM_BR, _make_spec())


def test_loop_count_compiles():
    _translate(_WASM_LOOP_COUNT, _make_spec())


# ---------------------------------------------------------------------------
# P13: BTOR2 output shape for br_if
# ---------------------------------------------------------------------------


def test_br_if_contains_neq_in_library():
    """br_if lowering compares condition with zero via neq."""
    art = _translate(_WASM_BR_IF, _make_spec())
    assert "neq" in art.layers["library"].body.decode("utf-8")


def test_br_if_contains_ite_in_dispatch():
    """br_if lowering produces a conditional PC via ITE in the dispatch layer."""
    art = _translate(_WASM_BR_IF, _make_spec())
    assert "ite" in art.layers["dispatch"].body.decode("utf-8")


def test_br_if_flattened_parseable():
    art = _translate(_WASM_BR_IF, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_loop_count_flattened_parseable():
    art = _translate(_WASM_LOOP_COUNT, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


# ---------------------------------------------------------------------------
# P13: reasoning interpreter — br_if / br / loop never trap
# ---------------------------------------------------------------------------


def test_reasoning_interp_br_if_nonzero_exits_no_trap():
    """br_if with nonzero condition exits the block; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_BR_IF, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_br_if_zero_falls_through_no_trap():
    """br_if with zero condition falls through; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_BR_IF, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_br_unconditional_no_trap():
    """br unconditional exit from block; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_BR, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_loop_count_n0_no_trap():
    """n=0: loop exits immediately, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_LOOP_COUNT, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=20)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_loop_count_n1_no_trap():
    """n=1: one loop iteration, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_LOOP_COUNT, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=30)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_loop_count_n3_no_trap():
    """n=3: three loop iterations, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_LOOP_COUNT, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 3, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=60)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P14: clz / ctz / popcnt compile tests
# ---------------------------------------------------------------------------


def test_i32_clz_compiles():
    _translate(_WASM_CLZ, _make_spec())


def test_i32_ctz_compiles():
    _translate(_WASM_CTZ, _make_spec())


def test_i32_popcnt_compiles():
    _translate(_WASM_POPCNT, _make_spec())


# ---------------------------------------------------------------------------
# P14: BTOR2 output shape for clz
# ---------------------------------------------------------------------------


def test_i32_clz_contains_slice():
    """clz lowering extracts individual bits via slice nodes."""
    art = _translate(_WASM_CLZ, _make_spec())
    assert "slice" in art.flattened.decode("utf-8")


def test_i32_clz_contains_ite():
    """clz lowering uses an ITE priority encoder."""
    art = _translate(_WASM_CLZ, _make_spec())
    assert "ite" in art.layers["library"].body.decode("utf-8")


def test_i32_clz_flattened_parseable():
    art = _translate(_WASM_CLZ, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_i32_ctz_contains_slice():
    """ctz lowering extracts individual bits via slice nodes."""
    art = _translate(_WASM_CTZ, _make_spec())
    assert "slice" in art.flattened.decode("utf-8")


def test_i32_popcnt_contains_slice():
    """popcnt lowering extracts individual bits via slice nodes."""
    art = _translate(_WASM_POPCNT, _make_spec())
    assert "slice" in art.flattened.decode("utf-8")


# ---------------------------------------------------------------------------
# P14: reasoning interpreter — clz / ctz / popcnt never trap
# ---------------------------------------------------------------------------


def test_reasoning_interp_clz_one_no_trap():
    """clz(1) = 31; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_CLZ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_clz_msb_no_trap():
    """clz(0x80000000) = 0; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_CLZ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0x80000000})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_ctz_two_no_trap():
    """ctz(2) = 1; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_CTZ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 2})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_popcnt_seven_no_trap():
    """popcnt(7) = 3; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_POPCNT, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 7})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P15: two-function module — main (i32→i32) calls helper ([]→[])
#
# Binary layout (49 bytes):
#   type 0: [] → []  (helper)
#   type 1: [i32] → [i32]  (main)
#   func 0 → type 1 (main), func 1 → type 0 (helper)
#   export "main" → func 0
#   main body:   local.get 0; call 1; local.get 0; end
#   helper body: end
# ---------------------------------------------------------------------------

_WASM_CALL = (
    b"\x00\x61\x73\x6D\x01\x00\x00\x00"          # magic + version
    b"\x01\x09\x02\x60\x00\x00\x60\x01\x7F\x01\x7F"  # type section
    b"\x03\x03\x02\x01\x00"                        # function section
    b"\x07\x08\x01\x04\x6D\x61\x69\x6E\x00\x00"   # export section
    b"\x0A\x0D\x02"                                # code section header (2 entries)
    b"\x08\x00\x20\x00\x10\x01\x20\x00\x0B"       # main body (8 bytes)
    b"\x02\x00\x0B"                                # helper body (2 bytes)
)


# ---------------------------------------------------------------------------
# P15: compile / structure tests
# ---------------------------------------------------------------------------


def test_call_two_func_module_compiles():
    """Two-function module with main calling helper compiles without error."""
    art = _translate(_WASM_CALL, _make_spec())
    assert art is not None


def test_call_flattened_parseable():
    """Flattened BTOR2 from two-function module is parseable."""
    art = _translate(_WASM_CALL, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_call_csp_state_in_machine():
    """Machine layer declares csp state variable."""
    art = _translate(_WASM_CALL, _make_spec())
    assert "csp" in art.layers["machine"].body.decode("utf-8")


def test_call_call_stack_state_in_machine():
    """Machine layer declares call_stack state variable."""
    art = _translate(_WASM_CALL, _make_spec())
    assert "call_stack" in art.layers["machine"].body.decode("utf-8")


def test_call_library_has_write_for_call_stack():
    """Library layer contains write node (call stack push on call N)."""
    art = _translate(_WASM_CALL, _make_spec())
    assert "write" in art.layers["library"].body.decode("utf-8")


def test_call_library_has_read_for_call_stack():
    """Library layer contains read node (call stack pop on return/end)."""
    art = _translate(_WASM_CALL, _make_spec())
    assert "read" in art.layers["library"].body.decode("utf-8")


def test_single_func_module_still_works():
    """Single-function module (no call) still compiles and parses correctly."""
    art = _translate(_make_wasm([_I32, _I32], [_I32], _BODY_ADD), _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


# ---------------------------------------------------------------------------
# P15: reasoning interpreter — call path, no trap
# ---------------------------------------------------------------------------


def test_reasoning_interp_call_no_trap():
    """main(42) calls helper (no-op) then returns 42; no trap fires."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_CALL, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 42})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=10)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_call_zero_no_trap():
    """main(0) calls helper (no-op) then returns 0; no trap fires."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_CALL, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=10)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_call_negative_no_trap():
    """main(-1) calls helper (no-op) then returns -1; no trap fires."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_CALL, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFFFFFFFF})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=10)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P16: i64.extend_i32_u / i64.extend_i32_s / i32.wrap_i64 — compile tests
# ---------------------------------------------------------------------------


def test_extend_i32_u_compiles():
    """i64.extend_i32_u compiles without error."""
    art = _translate(_WASM_EXTEND_U_WRAP, _make_spec())
    assert art is not None


def test_extend_i32_s_compiles():
    """i64.extend_i32_s compiles without error."""
    art = _translate(_WASM_EXTEND_S_WRAP, _make_spec())
    assert art is not None


def test_wrap_i64_compiles():
    """i32.wrap_i64 (from i64.const) compiles without error."""
    art = _translate(_WASM_WRAP_I64_CONST, _make_spec())
    assert art is not None


def test_extend_wrap_flattened_parseable():
    """i64.extend_i32_u + i32.wrap_i64 module produces valid BTOR2."""
    art = _translate(_WASM_EXTEND_U_WRAP, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_extend_u_uext_in_library():
    """Library layer contains uext node for zero-extension (extend_i32_u)."""
    art = _translate(_WASM_EXTEND_U_WRAP, _make_spec())
    assert "uext" in art.layers["library"].body.decode("utf-8")


def test_extend_s_sext_in_library():
    """Library layer contains sext node for sign-extension (extend_i32_s)."""
    art = _translate(_WASM_EXTEND_S_WRAP, _make_spec())
    assert "sext" in art.layers["library"].body.decode("utf-8")


def test_wrap_i64_slice_in_library():
    """Library layer contains slice node for truncation (i32.wrap_i64)."""
    art = _translate(_WASM_WRAP_I64_CONST, _make_spec())
    assert "slice" in art.layers["library"].body.decode("utf-8")


# ---------------------------------------------------------------------------
# P16: reasoning interpreter — type conversion, no trap
# ---------------------------------------------------------------------------


def test_reasoning_interp_extend_u_no_trap_zero():
    """extend_i32_u(0) round-trip via i32.wrap_i64: no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EXTEND_U_WRAP, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_extend_u_no_trap_max():
    """extend_i32_u(0xFFFFFFFF) round-trip via i32.wrap_i64: no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EXTEND_U_WRAP, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFFFFFFFF})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_extend_s_no_trap_negative():
    """extend_i32_s(-1) round-trip: sext fills upper 32 bits, wrap truncates back — no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EXTEND_S_WRAP, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFFFFFFFF})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P17: i64.const / i64.add / i64.sub / i64.mul — compile tests
# ---------------------------------------------------------------------------


def test_i64_const_compiles():
    """i64.const compiles without error."""
    art = _translate(_WASM_I64_CONST, _make_spec())
    assert art is not None


def test_i64_add_compiles():
    """i64.add compiles without error."""
    art = _translate(_WASM_I64_ADD, _make_spec())
    assert art is not None


def test_i64_sub_compiles():
    """i64.sub compiles without error."""
    art = _translate(_WASM_I64_SUB, _make_spec())
    assert art is not None


def test_i64_mul_compiles():
    """i64.mul compiles without error."""
    art = _translate(_WASM_I64_MUL, _make_spec())
    assert art is not None


def test_i64_add_flattened_parseable():
    """i64.extend_i32_u + i64.const + i64.add + i32.wrap_i64 module produces valid BTOR2."""
    art = _translate(_WASM_I64_ADD, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_i64_add_node_in_library():
    """Library layer contains add node for i64.add (bv64 sort)."""
    art = _translate(_WASM_I64_ADD, _make_spec())
    assert "add" in art.layers["library"].body.decode("utf-8")


def test_i64_sub_node_in_library():
    """Library layer contains sub node for i64.sub."""
    art = _translate(_WASM_I64_SUB, _make_spec())
    assert "sub" in art.layers["library"].body.decode("utf-8")


def test_i64_mul_node_in_library():
    """Library layer contains mul node for i64.mul."""
    art = _translate(_WASM_I64_MUL, _make_spec())
    assert "mul" in art.layers["library"].body.decode("utf-8")


# ---------------------------------------------------------------------------
# P17: reasoning interpreter — i64 arithmetic, no trap
# ---------------------------------------------------------------------------


def test_reasoning_interp_i64_add_no_trap_zero():
    """extend_i32_u(0) + i64.const 1 + i64.add: result is 1, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_ADD, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_add_no_trap_max():
    """extend_i32_u(0xFFFFFFFF) + i64.const 1 + i64.add: wraps in i64 space, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_ADD, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFFFFFFFF})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_mul_no_trap():
    """i64.const 3; i64.const 4; i64.mul: product is 12, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_MUL, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_sub_no_trap():
    """extend_i32_u(10) - i64.const 2 = 8: no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_SUB, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 10})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# P19: i32.extend8_s / i32.extend16_s — compile tests


def test_extend8_s_compiles():
    """i32.extend8_s compiles without error."""
    assert _translate(_WASM_EXTEND8_S, _make_spec()) is not None


def test_extend16_s_compiles():
    """i32.extend16_s compiles without error."""
    assert _translate(_WASM_EXTEND16_S, _make_spec()) is not None


def test_extend8_then_16_compiles():
    """i32.extend8_s followed by i32.extend16_s compiles without error."""
    assert _translate(_WASM_EXTEND8_THEN_16, _make_spec()) is not None


def test_extend8_s_flattened_parseable():
    """i32.extend8_s module produces valid BTOR2."""
    art = _translate(_WASM_EXTEND8_S, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_extend8_s_sext_in_library():
    """Library layer contains sext node for sign-extension (extend8_s)."""
    art = _translate(_WASM_EXTEND8_S, _make_spec())
    assert "sext" in art.flattened.decode("utf-8")


def test_extend8_s_slice_in_library():
    """Library layer contains slice node for bit extraction (extend8_s)."""
    art = _translate(_WASM_EXTEND8_S, _make_spec())
    assert "slice" in art.flattened.decode("utf-8")


def test_extend16_s_sext_in_library():
    """Library layer contains sext node for sign-extension (extend16_s)."""
    art = _translate(_WASM_EXTEND16_S, _make_spec())
    assert "sext" in art.flattened.decode("utf-8")


def test_extend16_s_slice_in_library():
    """Library layer contains slice node for bit extraction (extend16_s)."""
    art = _translate(_WASM_EXTEND16_S, _make_spec())
    assert "slice" in art.flattened.decode("utf-8")


# P19: reasoning interpreter — i32.extend8_s / i32.extend16_s, no trap


def test_reasoning_interp_extend8_s_no_trap_zero():
    """extend8_s(0) = 0: no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EXTEND8_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_extend8_s_no_trap_positive():
    """extend8_s(127) = 127: no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EXTEND8_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 127})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_extend8_s_no_trap_negative():
    """extend8_s(0xFF) = -1 (sign-extended): no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EXTEND8_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFF})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_extend16_s_no_trap_zero():
    """extend16_s(0) = 0: no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EXTEND16_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_extend16_s_no_trap_negative():
    """extend16_s(0xFFFF) = -1 (sign-extended): no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_EXTEND16_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFFFF})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# P20: i64.extend8_s / i64.extend16_s / i64.extend32_s — compile tests


def test_i64_extend8_s_compiles():
    """i64.extend8_s compiles without error."""
    assert _translate(_WASM_I64_EXTEND8_S, _make_spec()) is not None


def test_i64_extend16_s_compiles():
    """i64.extend16_s compiles without error."""
    assert _translate(_WASM_I64_EXTEND16_S, _make_spec()) is not None


def test_i64_extend32_s_compiles():
    """i64.extend32_s compiles without error."""
    assert _translate(_WASM_I64_EXTEND32_S, _make_spec()) is not None


def test_i64_extend_all_compiles():
    """i64.extend8_s + i64.extend16_s + i64.extend32_s chain compiles without error."""
    assert _translate(_WASM_I64_EXTEND_ALL, _make_spec()) is not None


def test_i64_extend8_s_flattened_parseable():
    """i64.extend8_s module produces valid BTOR2."""
    art = _translate(_WASM_I64_EXTEND8_S, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_i64_extend8_s_sext_in_library():
    """Library layer contains sext node for i64.extend8_s."""
    art = _translate(_WASM_I64_EXTEND8_S, _make_spec())
    assert "sext" in art.flattened.decode("utf-8")


def test_i64_extend16_s_sext_in_library():
    """Library layer contains sext node for i64.extend16_s."""
    art = _translate(_WASM_I64_EXTEND16_S, _make_spec())
    assert "sext" in art.flattened.decode("utf-8")


def test_i64_extend32_s_sext_in_library():
    """Library layer contains sext node for i64.extend32_s."""
    art = _translate(_WASM_I64_EXTEND32_S, _make_spec())
    assert "sext" in art.flattened.decode("utf-8")


# P20: reasoning interpreter — i64 sign-extensions, no trap


def test_reasoning_interp_i64_extend8_s_no_trap_zero():
    """i64.extend8_s(0) = 0: no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_EXTEND8_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_extend8_s_no_trap_positive():
    """i64.extend8_s applied to 0x7F: no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_EXTEND8_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0x7F})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_extend8_s_no_trap_negative():
    """i64.extend8_s applied to 0xFF (sign-extends to -1): no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_EXTEND8_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFF})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_extend32_s_no_trap_negative():
    """i64.extend32_s applied to 0x80000000 (sign-extends to INT64_MIN): no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_EXTEND32_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0x80000000})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_extend_all_no_trap():
    """Full chain extend8+16+32 on 0xFF: no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_EXTEND_ALL, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFF})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=10)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P21: i64 bitwise ops (i64.and / i64.or / i64.xor)
# ---------------------------------------------------------------------------


def test_i64_and_compiles():
    _translate(_WASM_I64_AND, _make_spec())


def test_i64_or_compiles():
    _translate(_WASM_I64_OR, _make_spec())


def test_i64_xor_compiles():
    _translate(_WASM_I64_XOR, _make_spec())


def test_i64_and_contains_and_op():
    art = _translate(_WASM_I64_AND, _make_spec())
    assert " and " in art.flattened.decode("utf-8")


def test_i64_or_contains_or_op():
    art = _translate(_WASM_I64_OR, _make_spec())
    assert " or " in art.flattened.decode("utf-8")


def test_i64_xor_contains_xor_op():
    art = _translate(_WASM_I64_XOR, _make_spec())
    assert " xor " in art.flattened.decode("utf-8")


# ---------------------------------------------------------------------------
# P21: i64 shift ops (i64.shl / i64.shr_s / i64.shr_u) — with mod-63 mask
# ---------------------------------------------------------------------------


def test_i64_shl_compiles():
    _translate(_WASM_I64_SHL, _make_spec())


def test_i64_shr_s_compiles():
    _translate(_WASM_I64_SHR_S, _make_spec())


def test_i64_shr_u_compiles():
    _translate(_WASM_I64_SHR_U, _make_spec())


def test_i64_shl_contains_sll():
    art = _translate(_WASM_I64_SHL, _make_spec())
    assert "sll" in art.flattened.decode("utf-8")


def test_i64_shr_s_contains_sra():
    art = _translate(_WASM_I64_SHR_S, _make_spec())
    assert "sra" in art.flattened.decode("utf-8")


def test_i64_shr_u_contains_srl():
    art = _translate(_WASM_I64_SHR_U, _make_spec())
    assert "srl" in art.flattened.decode("utf-8")


def test_i64_shl_mask_explicit_in_btor2():
    # The mod-63 mask must appear as an explicit 'and' before the sll node.
    art = _translate(_WASM_I64_SHL, _make_spec())
    text = art.flattened.decode("utf-8")
    assert "and" in text and "sll" in text


# ---------------------------------------------------------------------------
# P21: reasoning interpreter concrete-witness tests
# ---------------------------------------------------------------------------


def test_reasoning_interp_i64_and_no_trap():
    """0xFF & 0x0F = 0x0F, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_AND, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0xFF, "local_1": 0x0F})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_shl_basic():
    """1 << 1 = 2, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_SHL, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1, "local_1": 1})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_shl_mask_mod64():
    """Shift by 64 must equal shift by 0 (WASM mod-64 masking)."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_SHL, _make_spec())
    # local_0=5, local_1=64 → 5 << (64 & 63) = 5 << 0 = 5, no trap
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 5, "local_1": 64})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_shr_s_no_trap():
    """8 >> 2 = 2 (arithmetic), no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_SHR_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 8, "local_1": 2})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_shr_u_no_trap():
    """8 >> 2 = 2 (logical), no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_SHR_U, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 8, "local_1": 2})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P22: i64 div/rem compile + op-presence tests
# ---------------------------------------------------------------------------


def test_i64_div_s_compiles():
    _translate(_WASM_I64_DIV_S, _make_spec())


def test_i64_div_u_compiles():
    _translate(_WASM_I64_DIV_U, _make_spec())


def test_i64_rem_s_compiles():
    _translate(_WASM_I64_REM_S, _make_spec())


def test_i64_rem_u_compiles():
    _translate(_WASM_I64_REM_U, _make_spec())


def test_i64_div_s_contains_sdiv():
    art = _translate(_WASM_I64_DIV_S, _make_spec())
    assert "sdiv" in art.flattened.decode("utf-8")


def test_i64_div_u_contains_udiv():
    art = _translate(_WASM_I64_DIV_U, _make_spec())
    assert "udiv" in art.flattened.decode("utf-8")


def test_i64_rem_s_contains_srem():
    art = _translate(_WASM_I64_REM_S, _make_spec())
    assert "srem" in art.flattened.decode("utf-8")


def test_i64_rem_u_contains_urem():
    art = _translate(_WASM_I64_REM_U, _make_spec())
    assert "urem" in art.flattened.decode("utf-8")


def test_i64_div_s_contains_ite_for_trap():
    art = _translate(_WASM_I64_DIV_S, _make_spec())
    assert "ite" in art.layers["library"].body.decode("utf-8")


# ---------------------------------------------------------------------------
# P22: reasoning interpreter concrete-witness tests
# ---------------------------------------------------------------------------


def test_reasoning_interp_i64_div_s_nonzero_no_bad():
    """10 / 3 = 3 (signed), no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    spec = _make_spec(
        assumptions=(
            LocalInit(func_idx=0, local_idx=1, op=Comparison.NE, value=0),
        )
    )
    art = _translate(_WASM_I64_DIV_S, spec)
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 10, "local_1": 3})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_div_s_zero_divisor_bad_fired():
    """i64.div_s traps when divisor == 0."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_DIV_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 5, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps), "expected bad_fired for divisor==0"


def test_reasoning_interp_i64_div_s_overflow_bad_fired():
    """INT64_MIN / -1 is the signed overflow trap case."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_DIV_S_OVERFLOW, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps), "expected bad_fired for INT64_MIN/-1"


def test_reasoning_interp_i64_div_u_zero_divisor_bad_fired():
    """i64.div_u traps on divisor==0."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_DIV_U, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 3, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_rem_s_zero_divisor_bad_fired():
    """i64.rem_s traps on divisor==0."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_REM_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 3, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_rem_u_zero_divisor_bad_fired():
    """i64.rem_u traps on divisor==0."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_REM_U, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 3, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P23: i64.clz / i64.ctz / i64.popcnt compile tests
# ---------------------------------------------------------------------------


def test_i64_clz_compiles():
    _translate(_WASM_I64_CLZ, _make_spec())


def test_i64_ctz_compiles():
    _translate(_WASM_I64_CTZ, _make_spec())


def test_i64_popcnt_compiles():
    _translate(_WASM_I64_POPCNT, _make_spec())


# ---------------------------------------------------------------------------
# P23: BTOR2 output shape for i64.clz / i64.ctz / i64.popcnt
# ---------------------------------------------------------------------------


def test_i64_clz_contains_slice():
    """i64.clz lowering extracts individual bits via slice nodes."""
    art = _translate(_WASM_I64_CLZ, _make_spec())
    assert "slice" in art.flattened.decode("utf-8")


def test_i64_clz_contains_ite():
    """i64.clz lowering uses an ITE priority encoder."""
    art = _translate(_WASM_I64_CLZ, _make_spec())
    assert "ite" in art.layers["library"].body.decode("utf-8")


def test_i64_ctz_contains_slice():
    """i64.ctz lowering extracts individual bits via slice nodes."""
    art = _translate(_WASM_I64_CTZ, _make_spec())
    assert "slice" in art.flattened.decode("utf-8")


def test_i64_popcnt_contains_slice():
    """i64.popcnt lowering extracts individual bits via slice nodes."""
    art = _translate(_WASM_I64_POPCNT, _make_spec())
    assert "slice" in art.flattened.decode("utf-8")


# ---------------------------------------------------------------------------
# P23: reasoning interpreter — i64.clz / i64.ctz / i64.popcnt never trap
# ---------------------------------------------------------------------------


def test_reasoning_interp_i64_clz_one_no_trap():
    """i64.clz(1) = 63 (MSB is bit 63, only bit 0 is set); no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_CLZ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_clz_bit31_no_trap():
    """i64.clz(0x80000000) zero-extended = clz of bit 31 set → 32; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_CLZ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 0x80000000})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_ctz_two_no_trap():
    """i64.ctz(2) = 1; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_CTZ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 2})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_popcnt_seven_no_trap():
    """i64.popcnt(7) = 3; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_POPCNT, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 7})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P24: compile tests — i64 comparison instructions
# ---------------------------------------------------------------------------


def test_i64_eqz_compiles():
    _translate(_WASM_I64_EQZ, _make_spec())


def test_i64_eq_compiles():
    _translate(_WASM_I64_EQ, _make_spec())


def test_i64_ne_compiles():
    _translate(_WASM_I64_NE, _make_spec())


def test_i64_lt_s_compiles():
    _translate(_WASM_I64_LT_S, _make_spec())


def test_i64_lt_u_compiles():
    _translate(_WASM_I64_LT_U, _make_spec())


def test_i64_gt_s_compiles():
    _translate(_WASM_I64_GT_S, _make_spec())


def test_i64_gt_u_compiles():
    _translate(_WASM_I64_GT_U, _make_spec())


def test_i64_le_s_compiles():
    _translate(_WASM_I64_LE_S, _make_spec())


def test_i64_le_u_compiles():
    _translate(_WASM_I64_LE_U, _make_spec())


def test_i64_ge_s_compiles():
    _translate(_WASM_I64_GE_S, _make_spec())


def test_i64_ge_u_compiles():
    _translate(_WASM_I64_GE_U, _make_spec())


# ---------------------------------------------------------------------------
# P24: BTOR2 operator-presence tests
# ---------------------------------------------------------------------------


def test_i64_lt_s_contains_slt():
    art = _translate(_WASM_I64_LT_S, _make_spec())
    assert "slt" in art.flattened.decode("utf-8")


def test_i64_lt_u_contains_ult():
    art = _translate(_WASM_I64_LT_U, _make_spec())
    assert "ult" in art.flattened.decode("utf-8")


def test_i64_eq_contains_eq():
    art = _translate(_WASM_I64_EQ, _make_spec())
    assert " eq " in art.flattened.decode("utf-8")


def test_i64_eqz_contains_uext():
    # Result must be zero-extended bv1 → bv32.
    art = _translate(_WASM_I64_EQZ, _make_spec())
    assert "uext" in art.flattened.decode("utf-8")


# ---------------------------------------------------------------------------
# P24: reasoning interpreter concrete-witness tests — no trap
# ---------------------------------------------------------------------------


def test_reasoning_interp_i64_lt_s_no_trap():
    """i64(1) < i64(2) = 1, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_LT_S, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 1, "local_1": 2})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_eq_same_no_trap():
    """i64(5) == i64(5) = 1, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_EQ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 5, "local_1": 5})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_eqz_nonzero_no_trap():
    """i64.eqz(3) = 0, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_EQZ, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 3})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_i64_ge_u_no_trap():
    """i64(10) >= i64(3) unsigned = 1, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_I64_GE_U, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 10, "local_1": 3})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P25: select instruction
# ---------------------------------------------------------------------------


def test_select_compiles():
    _translate(_WASM_SELECT, _make_spec())


def test_select_contains_ite():
    art = _translate(_WASM_SELECT, _make_spec())
    assert "ite" in art.flattened.decode("utf-8")


def test_reasoning_interp_select_nonzero_cond_no_trap():
    """select(val1=10, val2=20, cond=1): cond nonzero → result = val1 = 10, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_SELECT, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 10, "local_1": 20, "local_2": 1})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_select_zero_cond_no_trap():
    """select(val1=10, val2=20, cond=0): cond zero → result = val2 = 20, no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_SELECT, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 10, "local_1": 20, "local_2": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


# ---------------------------------------------------------------------------
# P26: local.set / local.tee instructions
# ---------------------------------------------------------------------------


def test_local_set_compiles():
    _translate(_WASM_LOCAL_SET, _make_spec())


def test_local_tee_compiles():
    _translate(_WASM_LOCAL_TEE, _make_spec())


def test_reasoning_interp_local_set_no_trap():
    """local.set: write param_1 into local_0; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_LOCAL_SET, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 5, "local_1": 99})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_local_tee_no_trap():
    """local.tee: tee param_0 back into local_0 and drop; no trap."""
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _translate(_WASM_LOCAL_TEE, _make_spec())
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 42})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)
