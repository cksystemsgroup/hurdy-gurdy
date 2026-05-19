"""Tests for gurdy.pairs.wasm_btor2.source (decoder + WasmSource)."""

import pytest

from gurdy.pairs.wasm_btor2.source import WasmSource, WasmDecodeError, load_wasm_source
from gurdy.pairs.wasm_btor2.source.decoder import (
    BLOCKTYPE_VOID,
    I32, I64,
    KIND_FUNC,
    FuncType,
    WasmModule,
    decode_module,
)


# ---------------------------------------------------------------------------
# Minimal WASM binary builder (test helper)
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


def _type_sec(types: list[tuple[list[int], list[int]]]) -> bytes:
    body = _uleb(len(types))
    for params, results in types:
        body += bytes([0x60]) + _uleb(len(params)) + bytes(params) + _uleb(len(results)) + bytes(results)
    return _sec(1, body)


def _func_sec(type_idxs: list[int]) -> bytes:
    body = _uleb(len(type_idxs)) + bytes(type_idxs)
    return _sec(3, body)


def _mem_sec(min_pages: int, max_pages: int | None = None) -> bytes:
    if max_pages is None:
        body = _uleb(1) + bytes([0x00]) + _uleb(min_pages)
    else:
        body = _uleb(1) + bytes([0x01]) + _uleb(min_pages) + _uleb(max_pages)
    return _sec(5, body)


def _export_sec(exports: list[tuple[str, int, int]]) -> bytes:
    """exports: [(name, kind, idx), ...]"""
    body = _uleb(len(exports))
    for name, kind, idx in exports:
        body += _name(name) + bytes([kind]) + _uleb(idx)
    return _sec(7, body)


def _code_sec(bodies: list[bytes]) -> bytes:
    """bodies: list of raw instruction bytes (no locals prefix, no size prefix)."""
    entries = b""
    for b in bodies:
        entry = bytes([0x00]) + b  # 0 local groups + instructions
        entries += _uleb(len(entry)) + entry
    return _sec(10, _uleb(len(bodies)) + entries)


def _wasm(*sections: bytes) -> bytes:
    return b"\x00asm\x01\x00\x00\x00" + b"".join(sections)


# ---------------------------------------------------------------------------
# Helpers for common modules
# ---------------------------------------------------------------------------

def _mod_const42() -> bytes:
    """() -> (i32): returns 42."""
    types = _type_sec([([], [I32])])
    funcs = _func_sec([0])
    exports = _export_sec([("main", KIND_FUNC, 0)])
    code = _code_sec([bytes([0x41, 42, 0x0F, 0x0B])])  # i32.const 42; return; end
    return _wasm(types, funcs, exports, code)


def _mod_add_one() -> bytes:
    """(i32) -> (i32): returns arg + 1."""
    types = _type_sec([([I32], [I32])])
    funcs = _func_sec([0])
    exports = _export_sec([("add_one", KIND_FUNC, 0)])
    code = _code_sec([bytes([
        0x20, 0x00,  # local.get 0
        0x41, 0x01,  # i32.const 1
        0x6A,        # i32.add
        0x0F,        # return
        0x0B,        # end
    ])])
    return _wasm(types, funcs, exports, code)


def _mod_div_trap() -> bytes:
    """(i32) -> (i32): i32.const 10 / arg — traps when arg=0."""
    types = _type_sec([([I32], [I32])])
    funcs = _func_sec([0])
    exports = _export_sec([("div", KIND_FUNC, 0)])
    code = _code_sec([bytes([
        0x41, 0x0A,  # i32.const 10
        0x20, 0x00,  # local.get 0  (divisor)
        0x6D,        # i32.div_s
        0x0B,        # end
    ])])
    return _wasm(types, funcs, exports, code)


def _mod_add_loop() -> bytes:
    """(i32) -> (i32): sums integers 0..arg-1 using a loop."""
    # local 0 = arg (param), local 1 = counter, local 2 = sum
    # loop: while counter < arg: sum += counter; counter++
    types = _type_sec([([I32], [I32])])
    funcs = _func_sec([0])
    exports = _export_sec([("sum_n", KIND_FUNC, 0)])

    code_bytes = bytes([
        # 2 extra locals: i32 counter, i32 sum
        # locals declaration: groups=1, count=2, type=i32
        # But _code_sec doesn't add locals; let's use code_sec_with_locals below
    ])
    # We build the code entry manually with locals
    body = bytes([
        # no locals override: use the _code_sec_locals helper
    ])
    # Emit: locals_count=1, group=(count=2, type=i32)
    locals_bytes = bytes([0x01, 0x02, 0x7F])  # 1 group: 2 x i32
    instr = bytes([
        # counter (local 1) = 0 (already zeroed)
        # sum (local 2) = 0
        # loop:
        0x03, 0x40,        # loop (void)
          0x20, 0x01,      # local.get 1 (counter)
          0x20, 0x00,      # local.get 0 (arg)
          0x49,            # i32.lt_u
          0x04, 0x40,      # if (void)
            # sum += counter
            0x20, 0x02,    # local.get 2
            0x20, 0x01,    # local.get 1
            0x6A,          # i32.add
            0x21, 0x02,    # local.set 2
            # counter++
            0x20, 0x01,    # local.get 1
            0x41, 0x01,    # i32.const 1
            0x6A,          # i32.add
            0x21, 0x01,    # local.set 1
            # continue loop
            0x0C, 0x01,    # br 1 (the loop label is 1 level above the if)
          0x0B,            # end if
        0x0B,              # end loop
        # return sum
        0x20, 0x02,        # local.get 2
        0x0B,              # end (function)
    ])
    entry = locals_bytes + instr
    code_entry = _uleb(len(entry)) + entry
    code_sec = _sec(10, _uleb(1) + code_entry)
    return _wasm(types, funcs, exports, code_sec)


# ---------------------------------------------------------------------------
# Decoder tests
# ---------------------------------------------------------------------------


def test_magic_version_check():
    with pytest.raises(WasmDecodeError):
        decode_module(b"\x00\x00\x00\x00\x01\x00\x00\x00")  # bad magic


def test_too_short():
    with pytest.raises(WasmDecodeError):
        decode_module(b"\x00asm")


def test_minimal_empty_module():
    mod = decode_module(b"\x00asm\x01\x00\x00\x00")
    assert mod.types == []
    assert mod.imports == []
    assert mod.func_type_idxs == []
    assert mod.exports == []
    assert mod.codes == []


def test_decode_const42_module():
    data = _mod_const42()
    mod = decode_module(data)
    assert len(mod.types) == 1
    assert mod.types[0] == FuncType(params=(), results=(I32,))
    assert len(mod.func_type_idxs) == 1
    assert mod.func_type_idxs[0] == 0
    assert len(mod.exports) == 1
    assert mod.exports[0].name == "main"
    assert mod.exports[0].kind == KIND_FUNC
    assert mod.exports[0].index == 0
    assert len(mod.codes) == 1
    # Body should have i32.const, return, end
    ops = [i.op for i in mod.codes[0].body]
    assert "i32.const" in ops
    assert "end" in ops


def test_decode_add_one_module():
    data = _mod_add_one()
    mod = decode_module(data)
    assert mod.types[0] == FuncType(params=(I32,), results=(I32,))
    ops = [i.op for i in mod.codes[0].body]
    assert ops == ["local.get", "i32.const", "i32.add", "return", "end"]


def test_decode_with_memory():
    types = _type_sec([([], [])])
    funcs = _func_sec([0])
    mem = _mem_sec(1)
    exports = _export_sec([("f", KIND_FUNC, 0)])
    code = _code_sec([bytes([0x0B])])  # just end
    data = _wasm(types, funcs, mem, exports, code)
    mod = decode_module(data)
    assert len(mod.memories) == 1
    assert mod.memories[0].limits.min == 1
    assert mod.memories[0].limits.max is None


def test_branch_target_resolution_block():
    """block/end targets are resolved correctly."""
    # (i32) -> (i32): block; local.get 0; br 0; end; i32.const 0; end
    instr_bytes = bytes([
        0x02, 0x7F,  # block (i32)
          0x20, 0x00,  # local.get 0
          0x0C, 0x00,  # br 0
        0x0B,          # end block
        0x41, 0x00,    # i32.const 0
        0x0B,          # end function
    ])
    types = _type_sec([([I32], [I32])])
    funcs = _func_sec([0])
    exports = _export_sec([("f", KIND_FUNC, 0)])
    code = _code_sec([instr_bytes])
    mod = decode_module(_wasm(types, funcs, exports, code))
    body = mod.codes[0].body
    # body[0] is "block", its br_target should point to instr after end (index 4)
    block_instr = body[0]
    assert block_instr.op == "block"
    assert block_instr.br_target == 4  # after the block's end (index 3)


def test_branch_target_resolution_loop():
    """loop br_target points back to the loop instruction itself."""
    instr_bytes = bytes([
        0x03, 0x40,   # loop (void)
          0x0C, 0x00, # br 0
        0x0B,         # end loop
        0x0B,         # end function
    ])
    types = _type_sec([([], [])])
    funcs = _func_sec([0])
    exports = _export_sec([("f", KIND_FUNC, 0)])
    code = _code_sec([instr_bytes])
    mod = decode_module(_wasm(types, funcs, exports, code))
    body = mod.codes[0].body
    loop_instr = body[0]
    assert loop_instr.op == "loop"
    assert loop_instr.br_target == 0  # back to loop instruction


def test_branch_target_resolution_if_no_else():
    """if without else: br_target and alt both point to after end."""
    instr_bytes = bytes([
        0x04, 0x40,   # if (void)
          0x01,       # nop
        0x0B,         # end if
        0x0B,         # end function
    ])
    types = _type_sec([([I32], [])])
    funcs = _func_sec([0])
    exports = _export_sec([("f", KIND_FUNC, 0)])
    code = _code_sec([instr_bytes])
    mod = decode_module(_wasm(types, funcs, exports, code))
    body = mod.codes[0].body
    if_instr = body[0]
    assert if_instr.op == "if"
    assert if_instr.br_target == if_instr.alt  # both point after end


def test_branch_target_resolution_if_else():
    """if/else: if.alt points to else body start; br_target to after end."""
    instr_bytes = bytes([
        0x04, 0x7F,   # if (i32)
          0x41, 0x01, # i32.const 1   (true branch)
        0x05,          # else
          0x41, 0x00, # i32.const 0   (false branch)
        0x0B,          # end
        0x0B,          # end function
    ])
    types = _type_sec([([I32], [I32])])
    funcs = _func_sec([0])
    exports = _export_sec([("f", KIND_FUNC, 0)])
    code = _code_sec([instr_bytes])
    mod = decode_module(_wasm(types, funcs, exports, code))
    body = mod.codes[0].body
    if_instr = body[0]
    else_instr = body[2]          # else is at index 2 (after if + i32.const)
    assert if_instr.op == "if"
    assert else_instr.op == "else"
    # if.alt → first instruction of false branch = else_idx + 1 = 3
    assert if_instr.alt == 3
    # if.br_target → after the if block's end (index 4 → 5)
    assert if_instr.br_target == 5


# ---------------------------------------------------------------------------
# WasmSource tests
# ---------------------------------------------------------------------------


def test_wasm_source_export_lookup():
    src = load_wasm_source(_mod_const42())
    ex = src.export("main")
    assert ex is not None
    assert ex.kind == KIND_FUNC
    assert ex.index == 0
    assert src.export("nonexistent") is None


def test_wasm_source_func_type():
    src = load_wasm_source(_mod_add_one())
    ft = src.func_type(0)
    assert ft is not None
    assert ft.params == (I32,)
    assert ft.results == (I32,)


def test_wasm_source_content_hash():
    data = _mod_const42()
    src = load_wasm_source(data)
    assert src.content_hash is not None
    assert len(src.content_hash) == 64  # SHA-256 hex


def test_wasm_source_memory_info():
    types = _type_sec([([], [])])
    funcs = _func_sec([0])
    mem = _mem_sec(2)
    exports = _export_sec([("f", KIND_FUNC, 0)])
    code = _code_sec([bytes([0x0B])])
    src = load_wasm_source(_wasm(types, funcs, mem, exports, code))
    mi = src.memory_info()
    assert mi is not None
    assert mi.limits.min == 2


def test_wasm_source_no_memory():
    src = load_wasm_source(_mod_const42())
    assert src.memory_info() is None


def test_load_wasm_source_from_bytes():
    data = _mod_const42()
    src = load_wasm_source(data)
    assert src.content_hash is not None


def test_load_wasm_source_from_path(tmp_path):
    data = _mod_const42()
    p = tmp_path / "test.wasm"
    p.write_bytes(data)
    src = load_wasm_source(p)
    assert src.export("main") is not None
