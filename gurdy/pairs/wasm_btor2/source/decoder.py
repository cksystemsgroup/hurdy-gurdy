"""WASM 1.0 MVP binary format decoder.

Decodes a ``.wasm`` binary into a ``WasmModule`` containing pre-decoded
instruction lists (not raw bytes). Structured control-flow targets
(block/loop/if/else/end) are resolved during a second pass so the
interpreter never needs to scan forward.

Out of scope: SIMD, threads, reference types beyond funcref, GC proposal.
Float operations are decoded but will trap if executed (interpreter scope).
"""

from __future__ import annotations

from dataclasses import dataclass, field


WASM_MAGIC = b"\x00asm"
WASM_VERSION = b"\x01\x00\x00\x00"

# Value types (WASM 1.0)
I32 = 0x7F
I64 = 0x7E
F32 = 0x7D
F64 = 0x7C
FUNCREF = 0x70

BLOCKTYPE_VOID = 0x40  # empty block result

# Import/export descriptor kinds
KIND_FUNC = 0
KIND_TABLE = 1
KIND_MEM = 2
KIND_GLOBAL = 3

# Section IDs
_S_TYPE = 1
_S_IMPORT = 2
_S_FUNC = 3
_S_TABLE = 4
_S_MEM = 5
_S_GLOBAL = 6
_S_EXPORT = 7
_S_START = 8
_S_ELEM = 9
_S_CODE = 10
_S_DATA = 11


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class WasmDecodeError(ValueError):
    pass


class WasmTrap(RuntimeError):
    """Runtime trap — raised by the interpreter, not the decoder."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Instruction record
# ---------------------------------------------------------------------------


@dataclass
class Instr:
    """One decoded WASM instruction.

    ``op``: mnemonic string (e.g. ``"i32.add"``).
    ``imm``: tuple of decoded immediates.

    For structured control flow the two target fields are filled during the
    second-pass target resolution (see ``_resolve_targets``):

    ``br_target``: for block/if→ index of instruction *after* the matching
    end; for loop → index of the loop instruction itself (back-edge).
    ``alt``: for if → index of the else body start (or same as ``br_target``
    when there is no else); for else → same as if's ``br_target``.
    """

    op: str
    imm: tuple = ()
    br_target: int = -1
    alt: int = -1


# ---------------------------------------------------------------------------
# Module-level type definitions
# ---------------------------------------------------------------------------


@dataclass
class FuncType:
    params: tuple[int, ...]
    results: tuple[int, ...]


@dataclass
class Import:
    module: str
    name: str
    kind: int       # KIND_FUNC / KIND_TABLE / KIND_MEM / KIND_GLOBAL
    type_idx: int = -1  # valid for KIND_FUNC; others deferred


@dataclass
class Export:
    name: str
    kind: int       # KIND_FUNC etc
    index: int


@dataclass
class Limits:
    min: int
    max: int | None = None


@dataclass
class MemType:
    limits: Limits


@dataclass
class TableType:
    reftype: int
    limits: Limits


@dataclass
class GlobalType:
    valtype: int
    mutable: bool


@dataclass
class Global:
    gtype: GlobalType
    init: list[Instr]  # constant expression (evaluated at module init)


@dataclass
class LocalDecl:
    count: int
    valtype: int


@dataclass
class CodeEntry:
    locals: list[LocalDecl]
    body: list[Instr]  # jump targets resolved; final instr is ``end``


@dataclass
class DataSegment:
    memidx: int
    offset: list[Instr]  # constant-expression offset
    init: bytes


@dataclass
class WasmModule:
    types: list[FuncType] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    func_type_idxs: list[int] = field(default_factory=list)
    tables: list[TableType] = field(default_factory=list)
    memories: list[MemType] = field(default_factory=list)
    globals: list[Global] = field(default_factory=list)
    exports: list[Export] = field(default_factory=list)
    start: int | None = None
    codes: list[CodeEntry] = field(default_factory=list)
    data: list[DataSegment] = field(default_factory=list)

    @property
    def import_func_count(self) -> int:
        return sum(1 for i in self.imports if i.kind == KIND_FUNC)

    @property
    def total_func_count(self) -> int:
        return self.import_func_count + len(self.func_type_idxs)

    def func_type(self, func_idx: int) -> FuncType | None:
        n_imp = self.import_func_count
        if func_idx < n_imp:
            imp_funcs = [i for i in self.imports if i.kind == KIND_FUNC]
            if func_idx >= len(imp_funcs):
                return None
            tidx = imp_funcs[func_idx].type_idx
        else:
            local_idx = func_idx - n_imp
            if local_idx >= len(self.func_type_idxs):
                return None
            tidx = self.func_type_idxs[local_idx]
        return self.types[tidx] if tidx < len(self.types) else None


# ---------------------------------------------------------------------------
# LEB128 readers
# ---------------------------------------------------------------------------


def _uleb(data: bytes | memoryview, pos: int) -> tuple[int, int]:
    result, shift = 0, 0
    while True:
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            return result, pos


def _sleb(data: bytes | memoryview, pos: int) -> tuple[int, int]:
    result, shift = 0, 0
    while True:
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            if b & 0x40:
                result |= -(1 << shift)
            return result, pos


def _name(data: bytes | memoryview, pos: int) -> tuple[str, int]:
    n, pos = _uleb(data, pos)
    s = bytes(data[pos: pos + n]).decode("utf-8")
    return s, pos + n


# ---------------------------------------------------------------------------
# Immediate readers  (buf: bytes/memoryview, pos: int) -> (tuple, new_pos)
# ---------------------------------------------------------------------------


def _imm_none(buf: bytes, pos: int) -> tuple[tuple, int]:
    return (), pos


def _imm_blocktype(buf: bytes, pos: int) -> tuple[tuple, int]:
    bt = buf[pos]
    return (bt,), pos + 1


def _imm_leb(buf: bytes, pos: int) -> tuple[tuple, int]:
    v, pos = _uleb(buf, pos)
    return (v,), pos


def _imm_2leb(buf: bytes, pos: int) -> tuple[tuple, int]:
    a, pos = _uleb(buf, pos)
    b, pos = _uleb(buf, pos)
    return (a, b), pos


def _imm_br_table(buf: bytes, pos: int) -> tuple[tuple, int]:
    n, pos = _uleb(buf, pos)
    labels = []
    for _ in range(n):
        l, pos = _uleb(buf, pos)
        labels.append(l)
    default, pos = _uleb(buf, pos)
    return (tuple(labels), default), pos


def _imm_i32(buf: bytes, pos: int) -> tuple[tuple, int]:
    v, pos = _sleb(buf, pos)
    return (v,), pos


def _imm_i64(buf: bytes, pos: int) -> tuple[tuple, int]:
    v, pos = _sleb(buf, pos)
    return (v,), pos


def _imm_f32(buf: bytes, pos: int) -> tuple[tuple, int]:
    v = int.from_bytes(bytes(buf[pos: pos + 4]), "little")
    return (v,), pos + 4


def _imm_f64(buf: bytes, pos: int) -> tuple[tuple, int]:
    v = int.from_bytes(bytes(buf[pos: pos + 8]), "little")
    return (v,), pos + 8


def _imm_memarg(buf: bytes, pos: int) -> tuple[tuple, int]:
    align, pos = _uleb(buf, pos)
    offset, pos = _uleb(buf, pos)
    return (align, offset), pos


# ---------------------------------------------------------------------------
# Opcode dispatch table  opcode -> (mnemonic, imm_reader)
# ---------------------------------------------------------------------------

_NO = _imm_none
_BT = _imm_blocktype
_L1 = _imm_leb
_L2 = _imm_2leb
_I3 = _imm_i32
_I6 = _imm_i64
_F3 = _imm_f32
_F6 = _imm_f64
_MA = _imm_memarg
_BR = _imm_br_table

_OPCODE: dict[int, tuple[str, object]] = {
    0x00: ("unreachable", _NO),
    0x01: ("nop", _NO),
    0x02: ("block", _BT),
    0x03: ("loop", _BT),
    0x04: ("if", _BT),
    0x05: ("else", _NO),
    0x0B: ("end", _NO),
    0x0C: ("br", _L1),
    0x0D: ("br_if", _L1),
    0x0E: ("br_table", _BR),
    0x0F: ("return", _NO),
    0x10: ("call", _L1),
    0x11: ("call_indirect", _L2),
    0x1A: ("drop", _NO),
    0x1B: ("select", _NO),
    0x20: ("local.get", _L1),
    0x21: ("local.set", _L1),
    0x22: ("local.tee", _L1),
    0x23: ("global.get", _L1),
    0x24: ("global.set", _L1),
    0x28: ("i32.load", _MA),
    0x29: ("i64.load", _MA),
    0x2A: ("f32.load", _MA),
    0x2B: ("f64.load", _MA),
    0x2C: ("i32.load8_s", _MA),
    0x2D: ("i32.load8_u", _MA),
    0x2E: ("i32.load16_s", _MA),
    0x2F: ("i32.load16_u", _MA),
    0x30: ("i64.load8_s", _MA),
    0x31: ("i64.load8_u", _MA),
    0x32: ("i64.load16_s", _MA),
    0x33: ("i64.load16_u", _MA),
    0x34: ("i64.load32_s", _MA),
    0x35: ("i64.load32_u", _MA),
    0x36: ("i32.store", _MA),
    0x37: ("i64.store", _MA),
    0x38: ("f32.store", _MA),
    0x39: ("f64.store", _MA),
    0x3A: ("i32.store8", _MA),
    0x3B: ("i32.store16", _MA),
    0x3C: ("i64.store8", _MA),
    0x3D: ("i64.store16", _MA),
    0x3E: ("i64.store32", _MA),
    0x3F: ("memory.size", _L1),
    0x40: ("memory.grow", _L1),
    0x41: ("i32.const", _I3),
    0x42: ("i64.const", _I6),
    0x43: ("f32.const", _F3),
    0x44: ("f64.const", _F6),
    0x45: ("i32.eqz", _NO),
    0x46: ("i32.eq", _NO),
    0x47: ("i32.ne", _NO),
    0x48: ("i32.lt_s", _NO),
    0x49: ("i32.lt_u", _NO),
    0x4A: ("i32.gt_s", _NO),
    0x4B: ("i32.gt_u", _NO),
    0x4C: ("i32.le_s", _NO),
    0x4D: ("i32.le_u", _NO),
    0x4E: ("i32.ge_s", _NO),
    0x4F: ("i32.ge_u", _NO),
    0x50: ("i64.eqz", _NO),
    0x51: ("i64.eq", _NO),
    0x52: ("i64.ne", _NO),
    0x53: ("i64.lt_s", _NO),
    0x54: ("i64.lt_u", _NO),
    0x55: ("i64.gt_s", _NO),
    0x56: ("i64.gt_u", _NO),
    0x57: ("i64.le_s", _NO),
    0x58: ("i64.le_u", _NO),
    0x59: ("i64.ge_s", _NO),
    0x5A: ("i64.ge_u", _NO),
    0x5B: ("f32.eq", _NO),
    0x5C: ("f32.ne", _NO),
    0x5D: ("f32.lt", _NO),
    0x5E: ("f32.gt", _NO),
    0x5F: ("f32.le", _NO),
    0x60: ("f32.ge", _NO),
    0x61: ("f64.eq", _NO),
    0x62: ("f64.ne", _NO),
    0x63: ("f64.lt", _NO),
    0x64: ("f64.gt", _NO),
    0x65: ("f64.le", _NO),
    0x66: ("f64.ge", _NO),
    0x67: ("i32.clz", _NO),
    0x68: ("i32.ctz", _NO),
    0x69: ("i32.popcnt", _NO),
    0x6A: ("i32.add", _NO),
    0x6B: ("i32.sub", _NO),
    0x6C: ("i32.mul", _NO),
    0x6D: ("i32.div_s", _NO),
    0x6E: ("i32.div_u", _NO),
    0x6F: ("i32.rem_s", _NO),
    0x70: ("i32.rem_u", _NO),
    0x71: ("i32.and", _NO),
    0x72: ("i32.or", _NO),
    0x73: ("i32.xor", _NO),
    0x74: ("i32.shl", _NO),
    0x75: ("i32.shr_s", _NO),
    0x76: ("i32.shr_u", _NO),
    0x77: ("i32.rotl", _NO),
    0x78: ("i32.rotr", _NO),
    0x79: ("i64.clz", _NO),
    0x7A: ("i64.ctz", _NO),
    0x7B: ("i64.popcnt", _NO),
    0x7C: ("i64.add", _NO),
    0x7D: ("i64.sub", _NO),
    0x7E: ("i64.mul", _NO),
    0x7F: ("i64.div_s", _NO),
    0x80: ("i64.div_u", _NO),
    0x81: ("i64.rem_s", _NO),
    0x82: ("i64.rem_u", _NO),
    0x83: ("i64.and", _NO),
    0x84: ("i64.or", _NO),
    0x85: ("i64.xor", _NO),
    0x86: ("i64.shl", _NO),
    0x87: ("i64.shr_s", _NO),
    0x88: ("i64.shr_u", _NO),
    0x89: ("i64.rotl", _NO),
    0x8A: ("i64.rotr", _NO),
    # Float arithmetic 0x8B-0xA6: no immediates
    0x8B: ("f32.abs", _NO),    0x8C: ("f32.neg", _NO),
    0x8D: ("f32.ceil", _NO),   0x8E: ("f32.floor", _NO),
    0x8F: ("f32.trunc", _NO),  0x90: ("f32.nearest", _NO),
    0x91: ("f32.sqrt", _NO),   0x92: ("f32.add", _NO),
    0x93: ("f32.sub", _NO),    0x94: ("f32.mul", _NO),
    0x95: ("f32.div", _NO),    0x96: ("f32.min", _NO),
    0x97: ("f32.max", _NO),    0x98: ("f32.copysign", _NO),
    0x99: ("f64.abs", _NO),    0x9A: ("f64.neg", _NO),
    0x9B: ("f64.ceil", _NO),   0x9C: ("f64.floor", _NO),
    0x9D: ("f64.trunc", _NO),  0x9E: ("f64.nearest", _NO),
    0x9F: ("f64.sqrt", _NO),   0xA0: ("f64.add", _NO),
    0xA1: ("f64.sub", _NO),    0xA2: ("f64.mul", _NO),
    0xA3: ("f64.div", _NO),    0xA4: ("f64.min", _NO),
    0xA5: ("f64.max", _NO),    0xA6: ("f64.copysign", _NO),
    # Conversion ops: no immediates
    0xA7: ("i32.wrap_i64", _NO),
    0xA8: ("i32.trunc_f32_s", _NO),  0xA9: ("i32.trunc_f32_u", _NO),
    0xAA: ("i32.trunc_f64_s", _NO),  0xAB: ("i32.trunc_f64_u", _NO),
    0xAC: ("i64.extend_i32_s", _NO), 0xAD: ("i64.extend_i32_u", _NO),
    0xAE: ("i64.trunc_f32_s", _NO),  0xAF: ("i64.trunc_f32_u", _NO),
    0xB0: ("i64.trunc_f64_s", _NO),  0xB1: ("i64.trunc_f64_u", _NO),
    0xB2: ("f32.convert_i32_s", _NO), 0xB3: ("f32.convert_i32_u", _NO),
    0xB4: ("f32.convert_i64_s", _NO), 0xB5: ("f32.convert_i64_u", _NO),
    0xB6: ("f32.demote_f64", _NO),
    0xB7: ("f64.convert_i32_s", _NO), 0xB8: ("f64.convert_i32_u", _NO),
    0xB9: ("f64.convert_i64_s", _NO), 0xBA: ("f64.convert_i64_u", _NO),
    0xBB: ("f64.promote_f32", _NO),
    0xBC: ("i32.reinterpret_f32", _NO), 0xBD: ("i64.reinterpret_f64", _NO),
    0xBE: ("f32.reinterpret_i32", _NO), 0xBF: ("f64.reinterpret_i64", _NO),
}


# ---------------------------------------------------------------------------
# Instruction decoder
# ---------------------------------------------------------------------------


def _decode_expr(data: bytes, pos: int) -> tuple[list[Instr], int]:
    """Decode a constant expression (stops at the first ``end``)."""
    instrs: list[Instr] = []
    while pos < len(data):
        opcode = data[pos]; pos += 1
        if opcode == 0xFC:
            sub, pos = _uleb(data, pos)
            instrs.append(Instr(f"misc.{sub:#x}"))
            continue
        entry = _OPCODE.get(opcode)
        if entry is None:
            raise WasmDecodeError(f"unknown opcode {opcode:#04x} at byte {pos - 1}")
        mnemonic, imm_fn = entry
        imm, pos = imm_fn(data, pos)  # type: ignore[operator]
        instrs.append(Instr(mnemonic, imm))
        if mnemonic == "end":
            break
    return instrs, pos


def _decode_func_body(data: bytes, pos: int, body_end: int) -> tuple[list[Instr], int]:
    """Decode a function body (all instructions up to ``body_end`` bytes)."""
    instrs: list[Instr] = []
    while pos < body_end:
        opcode = data[pos]; pos += 1
        if opcode == 0xFC:
            sub, pos = _uleb(data, pos)
            instrs.append(Instr(f"misc.{sub:#x}"))
            continue
        entry = _OPCODE.get(opcode)
        if entry is None:
            raise WasmDecodeError(f"unknown opcode {opcode:#04x} at byte {pos - 1}")
        mnemonic, imm_fn = entry
        imm, pos = imm_fn(data, pos)  # type: ignore[operator]
        instrs.append(Instr(mnemonic, imm))
    return instrs, pos


def _resolve_targets(instrs: list[Instr]) -> None:
    """Second pass: fill in ``br_target`` / ``alt`` on control-flow instrs.

    Uses a stack of ``(kind, instr_index)`` entries where ``kind`` is one
    of ``"block"``, ``"loop"``, ``"if"``, ``"else"``.

    Pass 1 resolves block/loop/if/else/end.
    Pass 2 resolves br/br_if using the pre-resolved targets from pass 1.
    """
    # Pass 1: block/loop/if/else/end
    stack: list[tuple[str, int]] = []
    for i, ins in enumerate(instrs):
        if ins.op in ("block", "loop", "if"):
            stack.append((ins.op, i))
        elif ins.op == "else":
            # The matching "if" is at the top of the stack
            if stack and stack[-1][0] == "if":
                kind, if_idx = stack.pop()
                instrs[if_idx].alt = i + 1      # false branch: skip to else body
                stack.append(("else", if_idx))  # re-push with if_idx to close at end
            # else: malformed; leave unresolved
        elif ins.op == "end":
            if not stack:
                continue  # the function-level end; nothing to resolve
            kind, origin = stack.pop()
            after = i + 1
            if kind == "block":
                instrs[origin].br_target = after
            elif kind == "loop":
                instrs[origin].br_target = origin   # back-edge
            elif kind == "if":
                instrs[origin].br_target = after
                if instrs[origin].alt == -1:         # no else → false goes to after
                    instrs[origin].alt = after
            elif kind == "else":
                # origin is the index of the original "if" instruction
                if_idx = origin
                instrs[if_idx].br_target = after
                # The else instruction itself jumps to after when executed
                # Find the else instruction: it's the one that pushed ("else", if_idx)
                # We need to find the else instr between if_idx+1 and i
                for j in range(if_idx + 1, i):
                    if instrs[j].op == "else":
                        instrs[j].br_target = after
                        break

    # Pass 2: resolve br/br_if jump targets using the block/loop/if targets set above.
    # For br N / br_if N: look N levels up in the label stack; use that label's
    # pre-resolved br_target (loop → back-edge; block/if → instruction after end).
    stack2: list[tuple[str, int]] = []
    for i, ins in enumerate(instrs):
        if ins.op in ("block", "loop", "if"):
            stack2.append((ins.op, i))
        elif ins.op == "else":
            if stack2 and stack2[-1][0] == "if":
                _, if_idx = stack2.pop()
                stack2.append(("else", if_idx))
        elif ins.op == "end":
            if stack2:
                stack2.pop()
        elif ins.op in ("br", "br_if"):
            depth = ins.imm[0]
            if depth < len(stack2):
                _, origin = stack2[-1 - depth]
                ins.br_target = instrs[origin].br_target


# ---------------------------------------------------------------------------
# Section decoders
# ---------------------------------------------------------------------------


def _parse_type_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    count, pos = _uleb(data, pos)
    for _ in range(count):
        if data[pos] != 0x60:
            raise WasmDecodeError("functype must start with 0x60")
        pos += 1
        n_p, pos = _uleb(data, pos)
        params = tuple(data[pos: pos + n_p]); pos += n_p
        n_r, pos = _uleb(data, pos)
        results = tuple(data[pos: pos + n_r]); pos += n_r
        mod.types.append(FuncType(params, results))


def _parse_import_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    count, pos = _uleb(data, pos)
    for _ in range(count):
        mod_name, pos = _name(data, pos)
        field_name, pos = _name(data, pos)
        kind = data[pos]; pos += 1
        if kind == KIND_FUNC:
            tidx, pos = _uleb(data, pos)
            mod.imports.append(Import(mod_name, field_name, kind, tidx))
        elif kind == KIND_TABLE:
            reftype = data[pos]; pos += 1
            flag = data[pos]; pos += 1
            min_, pos = _uleb(data, pos)
            max_ = None
            if flag & 1:
                max_, pos = _uleb(data, pos)
            mod.imports.append(Import(mod_name, field_name, kind))
        elif kind == KIND_MEM:
            flag = data[pos]; pos += 1
            min_, pos = _uleb(data, pos)
            max_ = None
            if flag & 1:
                max_, pos = _uleb(data, pos)
            mod.imports.append(Import(mod_name, field_name, kind))
        elif kind == KIND_GLOBAL:
            _vt = data[pos]; pos += 1
            _mut = data[pos]; pos += 1
            mod.imports.append(Import(mod_name, field_name, kind))
        else:
            raise WasmDecodeError(f"unknown import kind {kind}")


def _parse_func_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    count, pos = _uleb(data, pos)
    for _ in range(count):
        tidx, pos = _uleb(data, pos)
        mod.func_type_idxs.append(tidx)


def _parse_table_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    count, pos = _uleb(data, pos)
    for _ in range(count):
        reftype = data[pos]; pos += 1
        flag = data[pos]; pos += 1
        min_, pos = _uleb(data, pos)
        max_ = None
        if flag & 1:
            max_, pos = _uleb(data, pos)
        mod.tables.append(TableType(reftype, Limits(min_, max_)))


def _parse_memory_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    count, pos = _uleb(data, pos)
    for _ in range(count):
        flag = data[pos]; pos += 1
        min_, pos = _uleb(data, pos)
        max_ = None
        if flag & 1:
            max_, pos = _uleb(data, pos)
        mod.memories.append(MemType(Limits(min_, max_)))


def _eval_const_expr(instrs: list[Instr]) -> int:
    """Evaluate a constant-expression (global init or data offset). Returns int."""
    for ins in instrs:
        if ins.op == "i32.const":
            return ins.imm[0] & 0xFFFFFFFF
        if ins.op == "i64.const":
            return ins.imm[0] & 0xFFFFFFFFFFFFFFFF
        if ins.op == "end":
            break
    return 0


def _parse_global_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    count, pos = _uleb(data, pos)
    for _ in range(count):
        valtype = data[pos]; pos += 1
        mutable = bool(data[pos]); pos += 1
        init_instrs, pos = _decode_expr(data, pos)
        _resolve_targets(init_instrs)
        mod.globals.append(Global(GlobalType(valtype, mutable), init_instrs))


def _parse_export_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    count, pos = _uleb(data, pos)
    for _ in range(count):
        n, pos = _name(data, pos)
        kind = data[pos]; pos += 1
        idx, pos = _uleb(data, pos)
        mod.exports.append(Export(n, kind, idx))


def _parse_start_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    fidx, pos = _uleb(data, pos)
    mod.start = fidx


def _parse_elem_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    # Skip element section (tables/function references) — not needed for P2
    pass


def _parse_code_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    count, pos = _uleb(data, pos)
    for _ in range(count):
        size, pos = _uleb(data, pos)
        body_end = pos + size
        # Parse locals
        n_local_groups, pos = _uleb(data, pos)
        local_decls: list[LocalDecl] = []
        for _ in range(n_local_groups):
            cnt, pos = _uleb(data, pos)
            vt = data[pos]; pos += 1
            local_decls.append(LocalDecl(cnt, vt))
        # Decode all instructions in the function body
        instrs, pos = _decode_func_body(data, pos, body_end)
        _resolve_targets(instrs)
        mod.codes.append(CodeEntry(local_decls, instrs))
        pos = body_end  # advance past any padding


def _parse_data_section(data: bytes, pos: int, end: int, mod: WasmModule) -> None:
    count, pos = _uleb(data, pos)
    for _ in range(count):
        memidx, pos = _uleb(data, pos)
        offset_instrs, pos = _decode_expr(data, pos)
        _resolve_targets(offset_instrs)
        n_bytes, pos = _uleb(data, pos)
        init = bytes(data[pos: pos + n_bytes]); pos += n_bytes
        mod.data.append(DataSegment(memidx, offset_instrs, init))


_SECTION_PARSERS = {
    _S_TYPE: _parse_type_section,
    _S_IMPORT: _parse_import_section,
    _S_FUNC: _parse_func_section,
    _S_TABLE: _parse_table_section,
    _S_MEM: _parse_memory_section,
    _S_GLOBAL: _parse_global_section,
    _S_EXPORT: _parse_export_section,
    _S_START: _parse_start_section,
    _S_ELEM: _parse_elem_section,
    _S_CODE: _parse_code_section,
    _S_DATA: _parse_data_section,
}


# ---------------------------------------------------------------------------
# Top-level decoder
# ---------------------------------------------------------------------------


def decode_module(data: bytes) -> WasmModule:
    """Decode a WASM 1.0 binary into a ``WasmModule``.

    Raises ``WasmDecodeError`` for format violations.
    """
    if len(data) < 8:
        raise WasmDecodeError("too short to be a WASM binary")
    if data[:4] != WASM_MAGIC:
        raise WasmDecodeError(f"bad magic: {data[:4].hex()}")
    if data[4:8] != WASM_VERSION:
        raise WasmDecodeError(f"unsupported version: {data[4:8].hex()}")

    pos = 8
    mod = WasmModule()
    while pos < len(data):
        sec_id = data[pos]; pos += 1
        sec_len, pos = _uleb(data, pos)
        sec_end = pos + sec_len
        parser = _SECTION_PARSERS.get(sec_id)
        if parser is not None:
            parser(data, pos, sec_end, mod)
        # unknown/custom sections are silently skipped
        pos = sec_end

    return mod


__all__ = [
    "BLOCKTYPE_VOID",
    "CodeEntry",
    "DataSegment",
    "Export",
    "F32", "F64",
    "FuncType",
    "Global",
    "GlobalType",
    "I32", "I64",
    "Import",
    "Instr",
    "KIND_FUNC", "KIND_GLOBAL", "KIND_MEM", "KIND_TABLE",
    "Limits",
    "LocalDecl",
    "MemType",
    "TableType",
    "WASM_MAGIC",
    "WasmDecodeError",
    "WasmModule",
    "WasmTrap",
    "decode_module",
    "_eval_const_expr",
]
