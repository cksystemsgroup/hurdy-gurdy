"""Invariant re-discharge (issue #2 route (b)): pono's ``--show-invar``
inductive invariant, re-discharged through the bridge's operator mapping
on independent SMT engines (``solvers/invariant.py``). Script construction
and name mapping are checked unconditionally; refutation controls run on
any host with an SMT backend; the end-to-end extraction is gated on pono
(and z3, whose disjoint lineage is what makes the check *independent*)."""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.languages.btor2.build import Builder
from gurdy.languages.btor2.model import from_text
from gurdy.solvers.invariant import (
    certify_unreachable,
    extract_invariant,
    frame_invariant,
    obligation_scripts,
    parse_invariant,
    redischarge_invariant,
)
from gurdy.solvers.pono_btor2 import find_pono


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


def _smt():
    from gurdy.solvers.inventory import available_smt_backends
    return bool(available_smt_backends())


def _even_counter():
    """An 8-bit counter from 0 stepping by 2; bad iff it equals 5 —
    unreachable at every depth, with evenness the 1-inductive certificate
    an IC3-class engine finds. Returns ``(text, state_id)`` — the state's
    *file* node id (the Builder renumbers on emission, and pono names by
    file id), read back from the emitted text."""
    b = Builder()
    c = b.state(8, "c")
    b.init(c, b.zero(8))
    b.next(c, b.op2("add", 8, c, b.constd(8, 2)))
    b.bad(b.op2("eq", 1, c, b.constd(8, 5)))
    text = b.to_text()
    return text, from_text(text).states()[0].id


def _plain_counter(target):
    """An 8-bit counter from 0 stepping by 1; bad iff it equals ``target``
    (reachable at step ``target``) — the no-invariant control."""
    b = Builder()
    c = b.state(8, "c")
    b.init(c, b.zero(8))
    b.next(c, b.op2("add", 8, c, b.one(8)))
    b.bad(b.op2("eq", 1, c, b.constd(8, target)))
    return b.to_text()


class TestObligationScripts(unittest.TestCase):
    def test_scripts_shape(self):
        # base/safe are one-frame, step is two-frame with the transition;
        # the invariant lands frame-mapped in each.
        text, c = _even_counter()
        scripts = obligation_scripts(
            text, f"(not (= ((_ extract 0 0) state{c}) #b1))")
        base, step, safe = scripts["base"], scripts["step"], scripts["safe"]
        for s in (base, step, safe):
            self.assertTrue(s.startswith(b"(set-logic QF_ABV)"))
            self.assertTrue(s.rstrip().endswith(b"(check-sat)"))
            self.assertIn(f"s{c}_0".encode(), s)
        self.assertIn(f"s{c}_1".encode(), step)      # transition frame
        self.assertNotIn(f"s{c}_1".encode(), base)   # base is initial-only
        self.assertNotIn(f"s{c}_1".encode(), safe)
        self.assertIn(b"(assert (not (not (=", base)  # negated invariant
        # init constrains the state only in base; step constrains the
        # primed copy (the transition); safe leaves the state free.
        self.assertIn(f"(assert (= s{c}_0".encode(), base)
        self.assertIn(f"(assert (= s{c}_1".encode(), step)
        self.assertNotIn(f"(assert (= s{c}_0".encode(), safe)

    def test_frame_mapping_rejects_unknown_node(self):
        # An unmapped pono name must never reach a solver as a free
        # variable — that would discharge vacuously.
        text, _ = _even_counter()
        with self.assertRaises(Unsupported):
            frame_invariant(text, "(= state999 #b00000000)", 0)

    def test_prop_out_of_range(self):
        text, _ = _even_counter()
        with self.assertRaises(ValueError):
            obligation_scripts(text, "true", prop=1)

    def test_parse_invariant(self):
        self.assertEqual(parse_invariant("INVAR: (and true x)\nunsat\n"),
                         "(and true x)")
        # A printer that wraps the s-expression is re-balanced.
        self.assertEqual(parse_invariant("INVAR: (and\ntrue x)\nunsat\n"),
                         "(and true x)")
        self.assertIsNone(parse_invariant("unsat\n"))


@unittest.skipUnless(_smt(), "no SMT backend available")
class TestRefutationControls(unittest.TestCase):
    """Negative controls (the drat-trim lesson): a certificate that fails
    an obligation must come back refuted, never silently upgraded."""

    def test_non_inductive_invariant_refutes_step(self):
        # "c != 5" holds initially and excludes the bad, but c=3 steps to
        # 5 — not inductive.
        text, c = _even_counter()
        res = redischarge_invariant(text, f"(not (= state{c} #b00000101))")
        self.assertFalse(res.ok)
        self.assertIsNone(res.tier)
        self.assertIn("step", res.refuted)

    def test_trivial_invariant_refutes_safe(self):
        # "true" is inductive but excludes nothing — the safe obligation
        # is the one that must catch it.
        text, _ = _even_counter()
        res = redischarge_invariant(text, "true")
        self.assertFalse(res.ok)
        self.assertIn("safe", res.refuted)


class TestEndToEnd(unittest.TestCase):
    @unittest.skipUnless(find_pono() and _z3(), "pono and/or z3 absent")
    def test_extract_and_redischarge(self):
        text, _ = _even_counter()
        inv = extract_invariant(text, mode="ic3bits", timeout_s=120)
        self.assertIsNotNone(inv, "ic3bits must prove the even counter "
                                  "and print its invariant")
        res = redischarge_invariant(text, inv)
        self.assertTrue(res.ok, msg=str(res.obligations))
        self.assertTrue(res.independent,
                        "z3 is lineage-disjoint from pono — the discharge "
                        "must count as independent")
        self.assertEqual(res.tier, "proved")
        self.assertIn("btor2-smtlib:operator-mapping", res.tcb)

    @unittest.skipUnless(find_pono() and _z3(), "pono and/or z3 absent")
    def test_certify_unreachable_end_to_end(self):
        text, _ = _even_counter()
        res = certify_unreachable(text, mode="ic3bits", timeout_s=120)
        self.assertTrue(res.ok, msg=str(res.obligations))
        self.assertEqual(res.tier, "proved")
        self.assertIsNotNone(res.invariant)

    @unittest.skipUnless(find_pono(), "pono absent")
    def test_reachable_yields_no_invariant(self):
        # A sat run carries a witness, not an invariant: extraction must
        # decline, never hand a bogus term downstream.
        self.assertIsNone(extract_invariant(_plain_counter(3),
                                            mode="ic3bits", timeout_s=120))


if __name__ == "__main__":
    unittest.main()
