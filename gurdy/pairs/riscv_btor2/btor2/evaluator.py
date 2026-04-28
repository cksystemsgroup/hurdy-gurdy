"""Concrete BTOR2 evaluator.

Given a ``Model`` and a binding from input/state nids to integer
values, compute every node's value. Used in tests to cross-check
the library's BTOR2 lowering against the Python simulator on
concrete inputs, without needing an external solver.

Only the subset of BTOR2 our library and translation actually emit
is supported; unknown ops raise ``NotImplementedError``.
"""

from __future__ import annotations

from gurdy.pairs.riscv_btor2.btor2.nodes import ArraySort, BitvecSort, Model, Node


def _mask(width: int) -> int:
    return (1 << width) - 1


def _sign_extend(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return (value ^ sign) - sign


def evaluate(
    model: Model,
    bindings: dict[int, int | dict[int, int]] | None = None,
) -> dict[int, int | dict[int, int]]:
    """Evaluate a (concrete-input) Model.

    ``bindings`` maps nid -> value for ``state``, ``input``, and
    ``constd``-style constants the caller wants to override. The
    result is a dict from nid to its computed value.

    Bitvector values are non-negative ints; arrays are dicts of
    ``{index: byte_value}``.
    """
    bindings = bindings or {}
    sort_widths: dict[int, int] = {}
    sort_kinds: dict[int, str] = {}  # 'bv' or 'array'
    array_meta: dict[int, tuple[int, int]] = {}  # idx_sort_nid, elt_sort_nid
    values: dict[int, int | dict[int, int]] = {}
    # Per-node sort/width book so concat / slice / sext can size correctly.
    node_sort: dict[int, int] = {}  # node nid -> sort nid
    node_width: dict[int, int] = {}  # node nid -> bv width (or 0 for array)

    def _record_sort(nid: int, sort_nid: int) -> None:
        node_sort[nid] = sort_nid
        if sort_kinds.get(sort_nid) == "bv":
            node_width[nid] = sort_widths[sort_nid]
        else:
            node_width[nid] = 0

    for node in model.nodes():
        op = node.op
        if op == "sort":
            if isinstance(node.sort, BitvecSort):
                sort_widths[node.nid] = node.sort.width
                sort_kinds[node.nid] = "bv"
            else:
                assert isinstance(node.sort, ArraySort)
                sort_kinds[node.nid] = "array"
                array_meta[node.nid] = (
                    node.sort.index_sort_nid,
                    node.sort.element_sort_nid,
                )
            continue

        # Inputs / states: must be in bindings.
        if op in {"input", "state"}:
            sort_nid = int(node.args[0])
            _record_sort(node.nid, sort_nid)
            if node.nid in bindings:
                values[node.nid] = bindings[node.nid]
            else:
                if sort_kinds.get(sort_nid) == "array":
                    values[node.nid] = {}
                else:
                    values[node.nid] = 0
            continue
        if op in {"init", "next", "bad", "constraint", "output"}:
            continue

        # Constants.
        if op == "zero":
            sort_nid = int(node.args[0])
            _record_sort(node.nid, sort_nid)
            values[node.nid] = 0
            continue
        if op == "one":
            sort_nid = int(node.args[0])
            _record_sort(node.nid, sort_nid)
            values[node.nid] = 1
            continue
        if op == "ones":
            sort_nid = int(node.args[0])
            _record_sort(node.nid, sort_nid)
            values[node.nid] = _mask(sort_widths[sort_nid])
            continue
        if op == "constd":
            sort_nid = int(node.args[0])
            _record_sort(node.nid, sort_nid)
            v = int(node.args[1])
            w = sort_widths[sort_nid]
            values[node.nid] = v & _mask(w)
            continue
        if op == "const":
            sort_nid = int(node.args[0])
            _record_sort(node.nid, sort_nid)
            v = int(node.args[1], 2)
            values[node.nid] = v & _mask(sort_widths[sort_nid])
            continue
        if op == "consth":
            sort_nid = int(node.args[0])
            _record_sort(node.nid, sort_nid)
            v = int(node.args[1], 16)
            values[node.nid] = v & _mask(sort_widths[sort_nid])
            continue

        result_sort = int(node.args[0])
        _record_sort(node.nid, result_sort)
        operand_nids = [int(a) for a in node.args[1:]]
        operands = [values.get(n, 0) for n in operand_nids]
        operand_widths = [node_width.get(n, 0) for n in operand_nids]

        v = _eval_op(op, operands, result_sort, sort_widths, sort_kinds, node, operand_widths)
        values[node.nid] = v

    return values


def _eval_op(op, operands, result_sort, sort_widths, sort_kinds, node, operand_widths=None):
    if op == "add":
        return (operands[0] + operands[1]) & _mask(sort_widths[result_sort])
    if op == "sub":
        return (operands[0] - operands[1]) & _mask(sort_widths[result_sort])
    if op == "mul":
        return (operands[0] * operands[1]) & _mask(sort_widths[result_sort])
    if op == "and":
        return (operands[0] & operands[1]) & _mask(sort_widths[result_sort])
    if op == "or":
        return (operands[0] | operands[1]) & _mask(sort_widths[result_sort])
    if op == "xor":
        return (operands[0] ^ operands[1]) & _mask(sort_widths[result_sort])
    if op == "not":
        return (~operands[0]) & _mask(sort_widths[result_sort])
    if op == "neg":
        return (-operands[0]) & _mask(sort_widths[result_sort])
    if op == "sll":
        w = sort_widths[result_sort]
        return (operands[0] << (operands[1] & (w - 1))) & _mask(w)
    if op == "srl":
        w = sort_widths[result_sort]
        return operands[0] >> (operands[1] & (w - 1))
    if op == "sra":
        w = sort_widths[result_sort]
        sv = _sign_extend(operands[0], w)
        return (sv >> (operands[1] & (w - 1))) & _mask(w)
    if op == "udiv":
        w = sort_widths[result_sort]
        if operands[1] == 0:
            return _mask(w)
        return (operands[0] // operands[1]) & _mask(w)
    if op == "urem":
        w = sort_widths[result_sort]
        if operands[1] == 0:
            return operands[0]
        return (operands[0] % operands[1]) & _mask(w)
    if op == "sdiv":
        w = sort_widths[result_sort]
        a = _sign_extend(operands[0], w)
        b = _sign_extend(operands[1], w)
        if b == 0:
            return _mask(w)  # treat as -1 in two's complement
        # Truncate-toward-zero division
        q = -(-a // b) if (a < 0) ^ (b < 0) and a % b != 0 else a // b
        return q & _mask(w)
    if op == "srem":
        w = sort_widths[result_sort]
        a = _sign_extend(operands[0], w)
        b = _sign_extend(operands[1], w)
        if b == 0:
            return operands[0]
        q = -(-a // b) if (a < 0) ^ (b < 0) and a % b != 0 else a // b
        return (a - q * b) & _mask(w)
    if op == "eq":
        return 1 if operands[0] == operands[1] else 0
    if op == "neq":
        return 0 if operands[0] == operands[1] else 1
    if op == "slt":
        w = operand_widths[0] if operand_widths else 64
        return 1 if _sign_extend(operands[0], w) < _sign_extend(operands[1], w) else 0
    if op == "sgt":
        w = operand_widths[0] if operand_widths else 64
        return 1 if _sign_extend(operands[0], w) > _sign_extend(operands[1], w) else 0
    if op == "slte":
        w = operand_widths[0] if operand_widths else 64
        return 1 if _sign_extend(operands[0], w) <= _sign_extend(operands[1], w) else 0
    if op == "sgte":
        w = operand_widths[0] if operand_widths else 64
        return 1 if _sign_extend(operands[0], w) >= _sign_extend(operands[1], w) else 0
    if op == "ult":
        return 1 if operands[0] < operands[1] else 0
    if op == "ugt":
        return 1 if operands[0] > operands[1] else 0
    if op == "ulte":
        return 1 if operands[0] <= operands[1] else 0
    if op == "ugte":
        return 1 if operands[0] >= operands[1] else 0
    if op == "ite":
        return operands[1] if operands[0] else operands[2]
    if op == "sext":
        target_w = sort_widths[result_sort]
        extra = int(node.args[2])
        if operand_widths and operand_widths[0]:
            in_w = operand_widths[0]
        else:
            in_w = target_w - extra
        return _sign_extend(operands[0], in_w) & _mask(target_w)
    if op == "uext":
        target_w = sort_widths[result_sort]
        return operands[0] & _mask(target_w)
    if op == "slice":
        hi = int(node.args[2])
        lo = int(node.args[3])
        w = hi - lo + 1
        return (operands[0] >> lo) & _mask(w)
    if op == "concat":
        # Operand 0 is high; operand 1 is low. BTOR2 spec.
        if operand_widths and operand_widths[1]:
            b_w = operand_widths[1]
        else:
            b_w = sort_widths[result_sort] // 2
        if operand_widths and operand_widths[0]:
            a_w = operand_widths[0]
        else:
            a_w = sort_widths[result_sort] - b_w
        return ((operands[0] & _mask(a_w)) << b_w) | (operands[1] & _mask(b_w))
    if op == "read":
        # array, index
        arr = operands[0] if isinstance(operands[0], dict) else {}
        return arr.get(operands[1], 0)
    if op == "write":
        arr = dict(operands[0]) if isinstance(operands[0], dict) else {}
        arr[operands[1]] = operands[2] & 0xFF
        return arr
    raise NotImplementedError(f"evaluator: unsupported op {op!r}")


__all__ = ["evaluate"]
