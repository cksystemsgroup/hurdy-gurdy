"""BTOR2 ``constraint`` enforcement (languages/btor2 brief; SOLVERS.md §4/§7).

The shared evaluator enforces constraints per the BTOR2 standard: each row
records ``constraint{id}`` beside ``bad{id}``, a violating row is the run's
last (truncation — no valid continuation), and a ``bad`` counts only on a
constraint-valid row. The bridge encodes the same per-frame reading (bad at
step j counts only with constraints holding at 0..j), so the evaluator, the
bridged z3 verdict, and a native checker (gated) agree on constrained
systems — including the two shapes that used to diverge:

* a system whose bad fires on a valid prefix *before* an inevitable later
  violation (the old global-constraint encoding masked the reach);
* a system whose bad is unreachable *only because of* the constraint (naive
  replay/sampling used to count the invalid-row bad as a reach).

Constraint-free systems are byte-for-byte untouched (the additive
guarantee); a bogus witness that fires bad only on an invalid row is
rejected by ``check_witness``.
"""

import unittest

from gurdy.core.solver import Verdict
from gurdy.languages.btor2.build import Builder
from gurdy.languages.btor2.eval import interpret
from gurdy.languages.btor2.model import from_text
from gurdy.languages.btor2.witness import check_witness, corroborate_unreach
from gurdy.pairs.btor2_smtlib import native_vs_bridged, reach
from gurdy.solvers.native_btor2 import (
    NativeBtor2Checker,
    find_btormc,
    find_native_checker,
)


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


def _guarded_counter():
    """A 4-bit counter from 0 constrained to stay below 3; bad iff it equals
    2. The bad fires at step 2 on a valid prefix; every run violates the
    constraint at step 3 — the shape whose reach a global-constraint
    encoding masks."""
    b = Builder()
    c = b.state(4, "c")
    b.init(c, b.zero(4))
    b.next(c, b.op2("add", 4, c, b.one(4)))
    b.constraint(b.op2("ult", 1, c, b.constd(4, 3)))
    b.bad(b.op2("eq", 1, c, b.constd(4, 2)))
    return b.to_text()


def _plain_counter():
    """The same counter with no constraint (the additive control)."""
    b = Builder()
    c = b.state(4, "c")
    b.init(c, b.zero(4))
    b.next(c, b.op2("add", 4, c, b.one(4)))
    b.bad(b.op2("eq", 1, c, b.constd(4, 2)))
    return b.to_text()


# bad = ¬g while the constraint requires g = 1: the bad is unreachable
# *only because of* the constraint.
_BLOCKED = "1 sort bitvec 1\n2 input 1 g\n3 constraint 2\n4 not 1 2\n5 bad 4\n"


class TestEvaluatorEnforcement(unittest.TestCase):
    def test_rows_record_constraint_and_truncate_on_violation(self):
        text = _guarded_counter()
        sys = from_text(text)
        cid, bid = sys.constraints()[0].id, sys.bads()[0].id
        trace = interpret(text, {"steps": 6})
        # rows 0..2 valid (c = 0, 1, 2; bad at 2); row 3 violates and is last
        self.assertEqual(len(trace), 4)
        self.assertEqual([row[f"constraint{cid}"] for row in trace], [1, 1, 1, 0])
        self.assertEqual([row[f"bad{bid}"] for row in trace], [0, 0, 1, 0])
        self.assertEqual([row["c"] for row in trace], [0, 1, 2, 3])

    def test_no_truncation_before_the_violating_step(self):
        trace = interpret(_guarded_counter(), {"steps": 3})
        self.assertEqual(len(trace), 3)
        self.assertTrue(all(v == 1 for row in trace for k, v in row.items()
                            if k.startswith("constraint")))

    def test_constraint_free_system_is_untouched(self):
        # the additive guarantee: no constraint keys, no truncation
        trace = interpret(_plain_counter(), {"steps": 6})
        self.assertEqual(len(trace), 6)
        self.assertFalse(any(k.startswith("constraint") for row in trace for k in row))

    def test_invalid_row_bad_is_not_a_reach(self):
        # default inputs drive g = 0: bad fires on the very row that violates
        # the constraint — an invalid row, truncated and not a reach.
        sys = from_text(_BLOCKED)
        cid, bid = sys.constraints()[0].id, sys.bads()[0].id
        trace = interpret(_BLOCKED, {"steps": 4})
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0][f"constraint{cid}"], 0)
        self.assertEqual(trace[0][f"bad{bid}"], 1)
        self.assertTrue(corroborate_unreach(_BLOCKED, k=3))


class TestWitnessValidity(unittest.TestCase):
    def test_bogus_invalid_row_witness_is_rejected(self):
        # a "witness" driving g = 0 fires bad only on a constraint-violating
        # row; a conformant native checker would never emit it.
        wit = "sat\nb0\n#0\n@0\n0 0 g@0\n.\n"
        self.assertFalse(check_witness(_BLOCKED, wit))

    def test_valid_prefix_witness_is_accepted_and_truncation_is_harmless(self):
        wit = "sat\nb0\n#0\n0 0000 c#0\n.\n"
        self.assertTrue(check_witness(_guarded_counter(), wit, k=2))
        # a longer replay truncates at the violation but keeps the valid reach
        self.assertTrue(check_witness(_guarded_counter(), wit, k=5))


@unittest.skipUnless(_z3(), "z3 not installed")
class TestBridgedVerdicts(unittest.TestCase):
    def test_reach_on_valid_prefix_before_inevitable_violation(self):
        # the encoding regression: global constraints over 0..5 would be
        # unsat here even though the bad fires at step 2 on a valid prefix.
        info = reach(_guarded_counter(), 5)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])

    def test_reach_respects_the_bound(self):
        self.assertEqual(reach(_guarded_counter(), 1)["verdict"], Verdict.UNREACHABLE)

    def test_constraint_blocks_the_bad(self):
        # unreachable only because of the constraint (without it the bad is
        # trivially reachable) — and the evaluator-side sampling agrees.
        info = reach(_BLOCKED, 3)
        self.assertEqual(info["verdict"], Verdict.UNREACHABLE)
        unconstrained = "1 sort bitvec 1\n2 input 1 g\n3 not 1 2\n4 bad 3\n"
        self.assertEqual(reach(unconstrained, 3)["verdict"], Verdict.REACHABLE)


@unittest.skipUnless(find_native_checker() and _z3(), "native checker and/or z3 absent")
class TestNativeVsBridgedConstrained(unittest.TestCase):
    def test_valid_prefix_reach_agrees(self):
        # the constrained addition to the native-vs-bridged corpus
        # (SOLVERS.md §7): the native checker finds the frame-2 witness
        # (constraints hold along its frames) and the bridged per-prefix
        # encoding agrees — the old global encoding answered unsat here.
        reached = native_vs_bridged(_guarded_counter(), 5)
        self.assertTrue(reached["agree"], msg=str(reached))
        self.assertEqual(reached["bridged"], Verdict.REACHABLE)


@unittest.skipUnless(find_btormc() and _z3(), "btormc and/or z3 absent")
class TestBoundedNativeConstrained(unittest.TestCase):
    def test_constraint_blocked_unreach_agrees_bounded(self):
        # the unreach side needs the *bounded* native claim (a BMC's clean
        # exhaustion, canary-controlled — decide() rightly stays UNKNOWN on
        # silence): btormc and the bridge agree the constraint blocks the bad.
        native = NativeBtor2Checker().decide_bounded(_BLOCKED, 3)
        self.assertEqual(native, Verdict.UNREACHABLE)
        self.assertEqual(reach(_BLOCKED, 3)["verdict"], Verdict.UNREACHABLE)


if __name__ == "__main__":
    unittest.main()
