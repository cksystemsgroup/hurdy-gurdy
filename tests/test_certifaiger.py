"""Certifaiger witness circuits (issue #2 route (b)): the BTOR2→AIGER
bit-blast (``languages/btor2/aiger.py``), the invariant→AIG compiler and
certificate emission (``solvers/certifaiger.py``). The bit-blast is
cross-checked against the shared BTOR2 evaluator by simulation — the
native-vs-bridged discipline, turned on our own emitter. Checker-backed
tests are gated on ``certifaiger-check`` (in the dev image; the negative
controls are the drat-trim lesson: an invalid witness must be rejected,
never silently validated) and the full route additionally on pono."""

import random
import unittest

from gurdy.core.errors import Unsupported
from gurdy.languages.btor2.aiger import FALSE, TRUE, Aig, bitblast
from gurdy.languages.btor2.build import Builder
from gurdy.languages.btor2.eval import interpret
from gurdy.languages.btor2.model import from_text
from gurdy.solvers.certifaiger import (
    _InvariantCompiler,
    certify_unreachable_aiger,
    check_witness_circuit,
    emit_certificate,
    find_certifaiger,
)
from gurdy.solvers.pono_btor2 import find_pono


def _even_counter():
    """The redischarge suite's fixture: an 8-bit counter from 0 stepping
    by 2; bad iff it equals 5 — unreachable, evenness the certificate."""
    b = Builder()
    c = b.state(8, "c")
    b.init(c, b.zero(8))
    b.next(c, b.op2("add", 8, c, b.constd(8, 2)))
    b.bad(b.op2("eq", 1, c, b.constd(8, 5)))
    text = b.to_text()
    return text, from_text(text).states()[0].id


def _plain_counter(target):
    b = Builder()
    c = b.state(8, "c")
    b.init(c, b.zero(8))
    b.next(c, b.op2("add", 8, c, b.one(8)))
    b.bad(b.op2("eq", 1, c, b.constd(8, target)))
    return b.to_text()


def _sim_aig(blasted, *, steps, inputs_by_cycle=None, uninit=None):
    """Simulate the blasted circuit: rows of per-cycle latch values (by
    latch literal), bad bits and constraint bits — the evaluator's shape.
    ``inputs_by_cycle``: cycle -> {input literal: bit}. ``uninit``: initial
    bit per uninitialized (reset == own literal) latch literal."""
    aig, inputs_by_cycle, uninit = blasted.aig, inputs_by_cycle or {}, uninit or {}
    cur = {}
    for latch in aig.latches:
        if latch.reset == latch.lit:
            cur[latch.lit] = uninit.get(latch.lit, 0)
        else:
            assert latch.reset in (FALSE, TRUE), "constant resets only"
            cur[latch.lit] = latch.reset
    rows = []
    for t in range(steps):
        val = {FALSE: 0, TRUE: 1}
        def setv(lit, v):
            val[lit], val[lit ^ 1] = v, 1 - v
        for lit, _sym in aig.inputs:
            setv(lit, inputs_by_cycle.get(t, {}).get(lit, 0))
        for latch in aig.latches:
            setv(latch.lit, cur[latch.lit])
        for lhs, rhs0, rhs1 in aig.ands:
            setv(lhs, val[rhs0] & val[rhs1])
        rows.append({"latches": dict(cur),
                     "bads": [val[b] for b in blasted.bads],
                     "constraints": [val[c] for c in blasted.constraints]})
        cur = {latch.lit: val[latch.next] for latch in aig.latches}
    return rows


def _eval_lit(blasted, lit, state_values):
    """Evaluate one literal combinationally with states bound to the given
    {state node id: int} values and inputs at 0 (invariant-compiler tests)."""
    val = {FALSE: 0, TRUE: 1}
    def setv(l, v):
        val[l], val[l ^ 1] = v, 1 - v
    for l, _sym in blasted.aig.inputs:
        setv(l, 0)
    for nid, bits in blasted.state_bits.items():
        v = state_values.get(nid, 0)
        for i, b in enumerate(bits):
            setv(b, (v >> i) & 1)
    for lhs, rhs0, rhs1 in blasted.aig.ands:
        setv(lhs, val[rhs0] & val[rhs1])
    return val[lit]


class TestAig(unittest.TestCase):
    def test_folding_and_hash_consing(self):
        aig = Aig()
        a, b = aig.add_input("a"), aig.add_input("b")
        self.assertEqual(aig.and_(a, FALSE), FALSE)
        self.assertEqual(aig.and_(TRUE, b), b)
        self.assertEqual(aig.and_(a, a), a)
        self.assertEqual(aig.and_(a, a ^ 1), FALSE)
        g = aig.and_(a, b)
        self.assertEqual(aig.and_(b, a), g)  # commuted: same gate
        self.assertEqual(len(aig.ands), 1)

    def test_io_before_gates(self):
        aig = Aig()
        a = aig.add_input()
        aig.add_latch()
        with self.assertRaises(Unsupported):
            aig.add_input()  # inputs must precede latches
        aig.and_(a, a ^ 1)
        # folding allocated no gate; a real gate freezes the layout
        b = aig.add_latch()
        aig.set_latch(b, next=a, reset=0)
        aig.and_(a, b)
        with self.assertRaises(Unsupported):
            aig.add_latch()

    def test_aag_emission(self):
        aig = Aig()
        a = aig.add_input("a")
        s = aig.add_latch("s")
        g = aig.and_(a, s)
        aig.set_latch(s, next=g, reset=1)
        out = aig.to_aag(bads=[g ^ 1])
        lines = out.splitlines()
        self.assertEqual(lines[0], "aag 3 1 1 0 1 1")
        self.assertEqual(lines[1], "2")        # input
        self.assertEqual(lines[2], "4 6 1")    # latch: next, reset 1
        self.assertEqual(lines[3], "7")        # bad (negated gate)
        self.assertEqual(lines[4], "6 4 2")    # and: lhs rhs0 rhs1
        self.assertIn("i0 a", lines)
        self.assertIn("l0 s", lines)


class TestBitblastSemantics(unittest.TestCase):
    """Random-input simulation equivalence against the shared evaluator."""

    def _crosscheck(self, text, *, steps=8, seeds=range(5), uninit_states=()):
        sys = from_text(text)
        blasted = bitblast(text)
        widths = {n.id: sys.sorts[n.sort].width
                  for n in sys.nodes.values() if n.op == "input"}
        bad_ids = [n.id for n in sys.bads()]
        con_ids = [n.id for n in sys.constraints()]
        states = [s for s in sys.states()]
        for seed in seeds:
            rng = random.Random(seed)
            ev_inputs, aig_inputs = {}, {}
            for t in range(steps):
                ev_inputs[t], aig_inputs[t] = {}, {}
                for nid, w in widths.items():
                    v = rng.randrange(1 << w)
                    ev_inputs[t][nid] = v
                    for i, lit in enumerate(blasted.input_bits[nid]):
                        aig_inputs[t][lit] = (v >> i) & 1
            overrides, uninit = {}, {}
            for s in states:
                if s.symbol in uninit_states:
                    v = rng.randrange(1 << widths.get(s.id, 8))
                    overrides[s.symbol] = v
                    for i, lit in enumerate(blasted.state_bits[s.id]):
                        uninit[lit] = (v >> i) & 1
            trace = interpret(text, {"steps": steps, "inputs": ev_inputs,
                                     "state": overrides})
            rows = _sim_aig(blasted, steps=steps, inputs_by_cycle=aig_inputs,
                            uninit=uninit)
            for i, ev_row in enumerate(trace):  # eval truncates on violation
                row = rows[i]
                for s in states:
                    got = sum(((row["latches"][lit]) << j) for j, lit
                              in enumerate(blasted.state_bits[s.id]))
                    self.assertEqual(got, ev_row[s.symbol or f"n{s.id}"],
                                     f"seed {seed} cycle {i} state {s.symbol}")
                for pos, nid in enumerate(bad_ids):
                    self.assertEqual(row["bads"][pos], ev_row[f"bad{nid}"],
                                     f"seed {seed} cycle {i} bad{nid}")
                for pos, nid in enumerate(con_ids):
                    self.assertEqual(row["constraints"][pos],
                                     ev_row[f"constraint{nid}"],
                                     f"seed {seed} cycle {i} constraint{nid}")

    def test_even_counter(self):
        text, _ = _even_counter()
        self._crosscheck(text, seeds=(0,))

    def test_arith_and_compare_medley(self):
        b = Builder()
        a = b.state(4, "a")
        c = b.state(4, "c")
        x = b.state(8, "acc")
        b.init(x, b.zero(8))
        # no init for a, c: uninitialized (free) latches
        b.next(a, b.op2("add", 4, a, b.one(4)))
        b.next(c, b.op2("xor", 4, c, a))
        mix = b.op2("mul", 4, a, c)
        mix = b.op2("sub", 4, mix, b.op1("neg", 4, a))
        mix = b.op2("or", 4, mix, b.op2("nand", 4, a, c))
        mix = b.op2("and", 4, mix, b.op2("nor", 4, a, b.op1("inc", 4, c)))
        mix = b.op2("xor", 4, mix, b.op1("dec", 4, b.op1("not", 4, a)))
        wide = b.op2("concat", 8, mix, b.op2("udiv", 4, a, c))
        wide = b.op2("add", 8, wide, b.uext(8, b.op2("urem", 4, c, a), 4))
        wide = b.op2("add", 8, wide, b.sext(8, b.slice(mix, 2, 1), 6))
        b.next(x, b.op2("add", 8, x, wide))
        for op in ("eq", "neq", "ult", "ulte", "ugt", "ugte",
                   "slt", "slte", "sgt", "sgte"):
            b.bad(b.op2(op, 1, a, c))
        for op in ("redor", "redand", "redxor"):
            b.bad(b.op1(op, 1, mix))
        b.bad(b.op2("implies", 1, b.op1("redor", 1, a), b.op1("redand", 1, c)))
        low = b.slice(wide, 3, 0)
        b.bad(b.slice(b.ite(4, b.op2("ult", 1, a, c), mix, low), 3, 3))
        self._crosscheck(b.to_text(), uninit_states=("a", "c"), seeds=range(8))

    def test_shift_medley(self):
        b = Builder()
        v = b.state(4, "v")
        s = b.state(4, "s")
        b.init(v, b.constd(4, 11))
        b.next(v, b.op2("add", 4, v, b.one(4)))
        b.next(s, b.op2("add", 4, s, b.one(4)))  # sweeps 0..15: saturation hit
        for op in ("sll", "srl", "sra"):
            r = b.op2(op, 4, v, s)
            b.bad(b.slice(r, 3, 3))
            b.bad(b.slice(r, 0, 0))
        self._crosscheck(b.to_text(), uninit_states=("s",), seeds=range(6))

    def test_constraint_truncation(self):
        b = Builder()
        c = b.state(4, "c")
        b.init(c, b.zero(4))
        b.next(c, b.op2("add", 4, c, b.one(4)))
        b.constraint(b.op2("ulte", 1, c, b.constd(4, 5)))
        b.bad(b.op2("eq", 1, c, b.constd(4, 3)))
        text = b.to_text()
        trace = interpret(text, {"steps": 10})
        self.assertLess(len(trace), 10)  # the constraint truncates the run
        self._crosscheck(text, steps=10, seeds=(0,))

    def test_negated_refs(self):
        text = ("1 sort bitvec 1\n"
                "2 zero 1\n"
                "3 state 1 s\n"
                "4 init 1 3 -2\n"   # init = NOT 0 = 1
                "5 next 1 3 -3\n"   # toggle via negated self reference
                "6 bad -3\n")
        self._crosscheck(text, seeds=(0,))

    def test_free_next_state_becomes_input(self):
        b = Builder()
        s = b.state(4, "s")  # no next: free in every step
        b.bad(b.op2("eq", 1, s, b.constd(4, 9)))
        blasted = bitblast(b.to_text())
        sid = from_text(b.to_text()).states()[0].id
        self.assertIn(sid, blasted.free_next)
        self.assertEqual(len(blasted.aig.inputs), 4)  # the fresh inputs
        latch_lits = {latch.lit for latch in blasted.aig.latches}
        for latch in blasted.aig.latches:
            self.assertNotIn(latch.next, latch_lits)  # not a self-loop

    def test_unsupported_constructs_abort(self):
        b = Builder()
        arr = b.state_array(4, 8, "mem")
        b.next_array(arr, arr)
        b.bad(b.op2("eq", 1, b.read(8, arr, b.zero(4)), b.zero(8)))
        with self.assertRaises(Unsupported):
            bitblast(b.to_text())
        b2 = Builder()
        s = b2.state(4, "s")
        b2.init(s, b2.op2("add", 4, b2.one(4), b2.one(4)))  # non-constant init
        b2.next(s, s)
        b2.bad(b2.op2("eq", 1, s, b2.zero(4)))
        with self.assertRaises(Unsupported):
            bitblast(b2.to_text())


class TestInvariantCompiler(unittest.TestCase):
    def _compile(self, term):
        text, c = _even_counter()
        blasted = bitblast(text)
        lit = _InvariantCompiler(blasted).compile_bool(term.format(c=c))
        return blasted, lit, c

    def test_pono_ic3bits_shape(self):
        # The literal shape a real `--show-invar` run prints for the fixture.
        blasted, lit, c = self._compile(
            "(and (and true (not (= ((_ extract 0 0) state{c}) #b1))) "
            "(not (= (bvcomp state{c} #b00000101) #b1)))")
        sid = blasted.system.states()[0].id
        for value, expect in ((0, 1), (2, 1), (4, 1), (6, 1),
                              (1, 0), (5, 0), (255, 0)):
            self.assertEqual(_eval_lit(blasted, lit, {sid: value}), expect,
                             f"invariant at c={value}")

    def test_let_and_indexed_constant(self):
        blasted, lit, _ = self._compile(
            "(let ((x (= state{c} (_ bv5 8)))) (not x))")
        sid = blasted.system.states()[0].id
        self.assertEqual(_eval_lit(blasted, lit, {sid: 5}), 0)
        self.assertEqual(_eval_lit(blasted, lit, {sid: 4}), 1)

    def test_bv_ops(self):
        blasted, lit, _ = self._compile(
            "(bvult (bvadd state{c} #x01) (bvmul #x02 (bvsub state{c} #x01)))")
        sid = blasted.system.states()[0].id
        for v in (0, 1, 2, 3, 4, 10, 200, 255):
            expect = 1 if (v + 1) % 256 < (2 * ((v - 1) % 256)) % 256 else 0
            self.assertEqual(_eval_lit(blasted, lit, {sid: v}), expect, f"c={v}")

    def test_unknown_node_rejected(self):
        # The frame_invariant discipline: an unmapped name must never
        # become an implicitly-free variable.
        with self.assertRaises(Unsupported):
            self._compile("(= state999 #b00000000)")

    def test_unsupported_op_rejected(self):
        with self.assertRaises(Unsupported):
            self._compile("(bvsdiv state{c} state{c})")

    def test_width_mismatch_rejected(self):
        with self.assertRaises(Unsupported):
            self._compile("(= state{c} #b1)")

    def test_non_boolean_invariant_rejected(self):
        with self.assertRaises(Unsupported):
            self._compile("state{c}")


class TestCertificateEmission(unittest.TestCase):
    def test_pair_shape_and_identity_mapping(self):
        text, c = _even_counter()
        model, witness = emit_certificate(
            text, [f"(not (= ((_ extract 0 0) state{c}) #b1))"])
        mlines, wlines = model.splitlines(), witness.splitlines()
        mh, wh = mlines[0].split(), wlines[0].split()
        self.assertEqual(mh[2], "0")            # no inputs
        self.assertEqual(mh[3], "8")            # 8 latch bits
        self.assertEqual(mh[6], "1")            # one bad
        self.assertEqual(wh[2:5], mh[2:5])      # same input/latch/output counts
        self.assertEqual(wh[6], "1")            # the invariant property
        n_latches = int(mh[3])
        self.assertEqual(mlines[1:1 + n_latches], wlines[1:1 + n_latches],
                         "latch sections (resets, nexts) must be identical")
        maps = [line for line in wlines if line.startswith("l")]
        self.assertEqual(len(maps), 8)
        for pos, latch in enumerate(bitblast(text).aig.latches):
            self.assertIn(f"l{pos} = {latch.lit}", maps)
        self.assertTrue(any("WITNESS" in line for line in wlines))

    def test_constraints_carried_to_both(self):
        b = Builder()
        s = b.state(4, "s")
        b.init(s, b.zero(4))
        b.next(s, b.op2("add", 4, s, b.one(4)))
        b.constraint(b.op2("ulte", 1, s, b.constd(4, 5)))
        b.bad(b.op2("eq", 1, s, b.constd(4, 9)))
        sid = from_text(b.to_text()).states()[0].id
        model, witness = emit_certificate(
            b.to_text(), [f"(bvule state{sid} (_ bv6 4))"])
        self.assertEqual(len(model.splitlines()[0].split()), 8)  # C section
        self.assertEqual(len(witness.splitlines()[0].split()), 8)

    def test_no_bad_rejected(self):
        b = Builder()
        s = b.state(4, "s")
        b.next(s, s)
        with self.assertRaises(ValueError):
            emit_certificate(b.to_text(), ["true"])


@unittest.skipUnless(find_certifaiger(), "certifaiger-check absent")
class TestCheckerControls(unittest.TestCase):
    """Certifaiger against emitted pairs (in the dev image). The negative
    controls are the point: a wrong invariant must be rejected."""

    def test_valid_witness_accepted(self):
        text, c = _even_counter()
        model, witness = emit_certificate(
            text, [f"(and (not (= ((_ extract 0 0) state{c}) #b1)) "
                   f"(not (= state{c} #b00000101)))"])
        ok, prov = check_witness_circuit(model, witness)
        self.assertTrue(ok, msg=prov["checker_output"])

    def test_non_inductive_invariant_rejected(self):
        # "c != 5" holds initially and excludes the bad, but 3 -> 5.
        text, c = _even_counter()
        model, witness = emit_certificate(
            text, [f"(not (= state{c} #b00000101))"])
        ok, prov = check_witness_circuit(model, witness)
        self.assertFalse(ok, msg=prov["checker_output"])

    def test_trivial_invariant_rejected(self):
        # "true" is inductive but does not imply the property.
        text, _ = _even_counter()
        model, witness = emit_certificate(text, ["true"])
        ok, prov = check_witness_circuit(model, witness)
        self.assertFalse(ok, msg=prov["checker_output"])


@unittest.skipUnless(find_pono() and find_certifaiger(),
                     "pono and/or certifaiger-check absent")
class TestEndToEnd(unittest.TestCase):
    def test_certify_unreachable_aiger(self):
        text, _ = _even_counter()
        res = certify_unreachable_aiger(text, mode="ic3bits", timeout_s=120)
        self.assertTrue(res.ok, msg=str(res.provenance))
        self.assertEqual(res.tier, "proved")
        self.assertTrue(res.checker_ok)
        self.assertIsNotNone(res.invariant)
        self.assertIn("hurdy-gurdy:btor2-aiger-bitblast", res.tcb)
        self.assertIn("kissat:sat", res.tcb)

    def test_reachable_yields_no_certificate(self):
        res = certify_unreachable_aiger(_plain_counter(3), mode="ic3bits",
                                        timeout_s=120)
        self.assertFalse(res.ok)
        self.assertIsNone(res.tier)
        self.assertIsNone(res.checker_ok)  # never reached the checker


if __name__ == "__main__":
    unittest.main()
