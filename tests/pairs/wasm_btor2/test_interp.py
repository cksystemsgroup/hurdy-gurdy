"""Tests for the WASM source interpreter (WasmSourceInterpreter)."""

import pytest

from gurdy.pairs.wasm_btor2.source import WasmSource, load_wasm_source
from gurdy.pairs.wasm_btor2.source.decoder import I32, I64, KIND_FUNC, decode_module
from gurdy.pairs.wasm_btor2.source_interp import WasmInputBinding, WasmSourceInterpreter
from gurdy.pairs.wasm_btor2.source_interp.bindings import FreeFieldNotAllowed


# ---------------------------------------------------------------------------
# Reuse binary builder from test_source (inline simpler version here)
# ---------------------------------------------------------------------------


def _uleb(n: int) -> bytes:
    out = []
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            break
    return bytes(out)


def _sleb(n: int) -> bytes:
    out = []
    more = True
    while more:
        b = n & 0x7F
        n >>= 7
        if (n == 0 and not (b & 0x40)) or (n == -1 and (b & 0x40)):
            more = False
        else:
            b |= 0x80
        out.append(b)
    return bytes(out)


def _name(s: str) -> bytes:
    b = s.encode("utf-8")
    return _uleb(len(b)) + b


def _sec(sec_id: int, body: bytes) -> bytes:
    return bytes([sec_id]) + _uleb(len(body)) + body


def _type_sec(types):
    body = _uleb(len(types))
    for params, results in types:
        body += bytes([0x60]) + _uleb(len(params)) + bytes(params) + _uleb(len(results)) + bytes(results)
    return _sec(1, body)


def _func_sec(type_idxs):
    return _sec(3, _uleb(len(type_idxs)) + bytes(type_idxs))


def _mem_sec(min_pages: int) -> bytes:
    return _sec(5, _uleb(1) + bytes([0x00]) + _uleb(min_pages))


def _export_sec(exports):
    body = _uleb(len(exports))
    for name, kind, idx in exports:
        body += _name(name) + bytes([kind]) + _uleb(idx)
    return _sec(7, body)


def _code_sec_raw(entries: list[bytes]) -> bytes:
    """entries: list of (locals_bytes + instr_bytes), size-prefixed."""
    body = _uleb(len(entries))
    for e in entries:
        body += _uleb(len(e)) + e
    return _sec(10, body)


def _wasm(*sections: bytes) -> bytes:
    return b"\x00asm\x01\x00\x00\x00" + b"".join(sections)


def _entry(locals_groups: list[tuple[int, int]], instr: bytes) -> bytes:
    """Build a code entry: locals declaration + instructions."""
    locs = _uleb(len(locals_groups))
    for cnt, vt in locals_groups:
        locs += _uleb(cnt) + bytes([vt])
    return locs + instr


# Interpreter singleton
_interp = WasmSourceInterpreter()


def _run(src: WasmSource, entry: str, params: dict[int, int] | None = None,
         max_steps: int = 500) -> tuple[list[int], str | None]:
    binding = WasmInputBinding(param_init=params or {})
    trace = _interp.run(src, binding, max_steps, entry_name=entry)
    results = trace.final_state.get("return_values", []) if trace.final_state else []
    return results, trace.halt_reason


# ---------------------------------------------------------------------------
# Basic execution tests
# ---------------------------------------------------------------------------


def test_const_return():
    """() -> i32: i32.const 42"""
    code = bytes([0x41, 42, 0x0B])  # i32.const 42; end
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([], [I32])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, halt = _run(src, "f")
    assert results == [42]
    assert halt == "halted"


def test_param_passthrough():
    """(i32) -> i32: local.get 0"""
    code = bytes([0x20, 0x00, 0x0B])  # local.get 0; end
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([I32], [I32])]),
        _func_sec([0]),
        _export_sec([("id", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "id", {0: 99})
    assert results == [99]


def test_i32_add():
    """(i32, i32) -> i32: local.get 0 + local.get 1."""
    code = bytes([0x20, 0x00, 0x20, 0x01, 0x6A, 0x0B])
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([I32, I32], [I32])]),
        _func_sec([0]),
        _export_sec([("add", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "add", {0: 7, 1: 35})
    assert results == [42]


def test_i32_add_wraparound():
    """i32.add wraps at 2^32."""
    code = bytes([0x20, 0x00, 0x20, 0x01, 0x6A, 0x0B])
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([I32, I32], [I32])]),
        _func_sec([0]),
        _export_sec([("add", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "add", {0: 0xFFFFFFFF, 1: 1})
    assert results == [0]


def test_i32_sub():
    code = bytes([0x20, 0x00, 0x20, 0x01, 0x6B, 0x0B])  # i32.sub
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([I32, I32], [I32])]),
        _func_sec([0]),
        _export_sec([("sub", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "sub", {0: 10, 1: 3})
    assert results == [7]


def test_i32_mul():
    code = bytes([0x20, 0x00, 0x20, 0x01, 0x6C, 0x0B])  # i32.mul
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([I32, I32], [I32])]),
        _func_sec([0]),
        _export_sec([("mul", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "mul", {0: 6, 1: 7})
    assert results == [42]


def test_i32_div_s():
    code = bytes([0x20, 0x00, 0x20, 0x01, 0x6D, 0x0B])  # i32.div_s
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([I32, I32], [I32])]),
        _func_sec([0]),
        _export_sec([("div", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "div", {0: 10, 1: 2})
    assert results == [5]
    # Negative: -7 / 2 = -3 (truncate toward zero)
    results2, _ = _run(src, "div", {0: 0xFFFFFFF9, 1: 2})  # -7 / 2
    assert results2 == [0xFFFFFFFD]  # -3 as u32


def test_i32_div_by_zero_traps():
    """i32.div_s with divisor=0 should trap."""
    code = bytes([0x20, 0x00, 0x41, 0x00, 0x6D, 0x0B])  # local.get 0; i32.const 0; i32.div_s
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([I32], [I32])]),
        _func_sec([0]),
        _export_sec([("div", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    _, halt = _run(src, "div", {0: 5})
    assert halt is not None and "divide" in halt


def test_i32_shl_mask():
    """i32.shl masks shift amount mod 32 (corpus seed 0004)."""
    # shift by 32 is equivalent to shift by 0
    code = bytes([0x20, 0x00, 0x20, 0x01, 0x74, 0x0B])  # i32.shl
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([I32, I32], [I32])]),
        _func_sec([0]),
        _export_sec([("shl", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "shl", {0: 1, 1: 32})  # 1 << 32 → 1 << 0 = 1
    assert results == [1]
    results2, _ = _run(src, "shl", {0: 1, 1: 1})
    assert results2 == [2]


def test_unreachable_traps():
    code = bytes([0x00, 0x0B])  # unreachable; end
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([], [])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    _, halt = _run(src, "f")
    assert halt == "unreachable"


def test_if_true_branch():
    """if: condition=1 → true branch returns 1."""
    instr = bytes([
        0x20, 0x00,        # local.get 0
        0x04, 0x7F,        # if (i32)
          0x41, 0x01,      # i32.const 1
        0x05,              # else
          0x41, 0x00,      # i32.const 0
        0x0B,              # end if
        0x0B,              # end function
    ])
    entry_bytes = _entry([], instr)
    src = load_wasm_source(_wasm(
        _type_sec([([I32], [I32])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "f", {0: 1})
    assert results == [1]


def test_if_false_branch():
    """if: condition=0 → false branch returns 0."""
    instr = bytes([
        0x20, 0x00,
        0x04, 0x7F,
          0x41, 0x01,
        0x05,
          0x41, 0x00,
        0x0B,
        0x0B,
    ])
    entry_bytes = _entry([], instr)
    src = load_wasm_source(_wasm(
        _type_sec([([I32], [I32])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "f", {0: 0})
    assert results == [0]


def test_loop_sum():
    """loop that sums 0..n-1 (corpus seed 0001 pattern)."""
    # locals: [0]=n(param), [1]=counter, [2]=acc
    instr = bytes([
        # loop:
        0x03, 0x40,        # loop void
          0x20, 0x01,      # local.get counter
          0x20, 0x00,      # local.get n
          0x49,            # i32.lt_u
          0x04, 0x40,      # if void
            0x20, 0x02,    # local.get acc
            0x20, 0x01,    # local.get counter
            0x6A,          # i32.add
            0x21, 0x02,    # local.set acc
            0x20, 0x01,    # local.get counter
            0x41, 0x01,    # i32.const 1
            0x6A,          # i32.add
            0x21, 0x01,    # local.set counter
            0x0C, 0x01,    # br 1 (back to loop)
          0x0B,            # end if
        0x0B,              # end loop
        0x20, 0x02,        # local.get acc
        0x0B,              # end fn
    ])
    entry_bytes = _entry([(2, I32)], instr)  # 2 extra i32 locals
    src = load_wasm_source(_wasm(
        _type_sec([([I32], [I32])]),
        _func_sec([0]),
        _export_sec([("sum", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, halt = _run(src, "sum", {0: 5})
    assert results == [10], f"expected 10 (0+1+2+3+4), got {results}, halt={halt}"
    results2, _ = _run(src, "sum", {0: 0})
    assert results2 == [0]


def test_memory_store_and_load():
    """i32.store then i32.load round-trip."""
    # memory[0] = arg; return memory[0]
    instr = bytes([
        0x41, 0x00,        # i32.const 0 (addr)
        0x20, 0x00,        # local.get 0 (value)
        0x36, 0x02, 0x00,  # i32.store align=2 offset=0
        0x41, 0x00,        # i32.const 0 (addr)
        0x28, 0x02, 0x00,  # i32.load align=2 offset=0
        0x0B,
    ])
    entry_bytes = _entry([], instr)
    src = load_wasm_source(_wasm(
        _type_sec([([I32], [I32])]),
        _func_sec([0]),
        _mem_sec(1),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "f", {0: 0xDEADBEEF})
    assert results == [0xDEADBEEF]


def test_memory_oob_traps():
    """Out-of-bounds memory access traps."""
    # Store at address that's past the end of 1 page (65536 bytes)
    instr = bytes([
        0x41] + list(_uleb(65536)) + [  # i32.const 65536
        0x20, 0x00,
        0x36, 0x02, 0x00,  # i32.store — OOB
        0x41, 0x00,
        0x0B,
    ])
    entry_bytes = _entry([], instr)
    src = load_wasm_source(_wasm(
        _type_sec([([I32], [I32])]),
        _func_sec([0]),
        _mem_sec(1),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    _, halt = _run(src, "f", {0: 42})
    assert halt is not None and "out of bounds" in halt


def test_local_tee():
    """local.tee peeks (does not pop) and writes local."""
    # result = local.tee(0, 7) * 2 — returns 7*2=14 but local[0] set to 7
    instr = bytes([
        0x41, 0x07,        # i32.const 7
        0x22, 0x00,        # local.tee 0
        0x41, 0x02,        # i32.const 2
        0x6C,              # i32.mul
        0x0B,
    ])
    entry_bytes = _entry([(1, I32)], instr)  # 1 extra local for param slot
    src = load_wasm_source(_wasm(
        _type_sec([([], [I32])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "f")
    assert results == [14]


def test_i32_wrap_i64():
    """i64 value wrapped to i32."""
    instr = bytes([
        0x42] + list(_sleb(0x1_FFFF_FFFF)) + [  # i64.const 0x1_FFFF_FFFF
        0xA7,  # i32.wrap_i64
        0x0B,
    ])
    entry_bytes = _entry([], instr)
    src = load_wasm_source(_wasm(
        _type_sec([([], [I32])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "f")
    assert results == [0xFFFFFFFF]


def test_i64_extend_i32_s():
    """Signed extension: -1 as i32 → -1 as i64 (0xFFFFFFFFFFFFFFFF)."""
    instr = bytes([
        0x41, 0x7F,   # i32.const -1 (LEB128: 0x7F = -1 as s7)
        0xAC,         # i64.extend_i32_s
        0x0B,
    ])
    entry_bytes = _entry([], instr)
    src = load_wasm_source(_wasm(
        _type_sec([([], [I64])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "f")
    assert results == [0xFFFFFFFFFFFFFFFF]


def test_i64_extend_i32_u():
    """Unsigned extension: 0xFFFFFFFF as i32 → 0x00000000FFFFFFFF as i64."""
    instr = bytes([
        0x41] + list(_sleb(-1)) + [  # i32.const -1 (= 0xFFFFFFFF as u32)
        0xAD,  # i64.extend_i32_u
        0x0B,
    ])
    entry_bytes = _entry([], instr)
    src = load_wasm_source(_wasm(
        _type_sec([([], [I64])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    results, _ = _run(src, "f")
    assert results == [0xFFFFFFFF]


def test_trace_records_steps():
    """SourceTrace has the expected number of steps."""
    code = bytes([0x41, 42, 0x0B])
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([], [I32])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    binding = WasmInputBinding()
    trace = _interp.run(src, binding, 100, entry_name="f")
    # i32.const + end = 2 steps
    assert len(trace.steps) == 2
    assert trace.steps[0].location["op"] == "i32.const"
    assert trace.steps[1].location["op"] == "end"


def test_shadow_mode():
    """record_shadow=True populates step deltas."""
    instr = bytes([0x41, 5, 0x21, 0x00, 0x0B])  # i32.const 5; local.set 0; end
    entry_bytes = _entry([(1, I32)], instr)
    src = load_wasm_source(_wasm(
        _type_sec([([], [])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    binding = WasmInputBinding()
    trace = _interp.run(src, binding, 100, entry_name="f", record_shadow=True)
    # One step should have local_write recorded
    ops = [s.location["op"] for s in trace.steps]
    assert "local.set" in ops
    # Find the local.set step and check its deltas
    ls_step = next(s for s in trace.steps if s.location["op"] == "local.set")
    assert ls_step.deltas is not None
    assert "local_write" in ls_step.deltas


def test_free_fields_require_shadow():
    """FREE binding without record_shadow raises FreeFieldNotAllowed."""
    from gurdy.pairs.wasm_btor2.source_interp.bindings import FREE
    code = bytes([0x41, 42, 0x0B])
    entry_bytes = _entry([], code)
    src = load_wasm_source(_wasm(
        _type_sec([([], [I32])]),
        _func_sec([0]),
        _export_sec([("f", KIND_FUNC, 0)]),
        _code_sec_raw([entry_bytes]),
    ))
    binding = WasmInputBinding(param_init={0: FREE})
    with pytest.raises(FreeFieldNotAllowed):
        _interp.run(src, binding, 100, entry_name="f")


def test_call_direct():
    """call instruction invokes a second local function."""
    # func 0: () -> i32: call func 1; return
    # func 1: () -> i32: i32.const 99; end
    types = _type_sec([([], [I32]), ([], [I32])])
    funcs = _func_sec([0, 1])
    exports = _export_sec([("f", KIND_FUNC, 0)])
    code0 = _entry([], bytes([0x10, 0x01, 0x0F, 0x0B]))          # call 1; return; end
    code1 = _entry([], bytes([0x41]) + _sleb(99) + bytes([0x0B]))  # i32.const 99; end
    src = load_wasm_source(_wasm(
        types, funcs, exports,
        _code_sec_raw([code0, code1]),
    ))
    results, halt = _run(src, "f")
    assert results == [99]
    assert halt == "halted"
