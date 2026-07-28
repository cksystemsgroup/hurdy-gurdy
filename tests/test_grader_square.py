"""The grader-authoritative square (gurdy/core/grader_square.py) — SCALING.md
§3.1's consequence: the grader rebuilds a pair's square from ``T``, ``Λ``, ``π``
and the trusted oracle, and **never calls the pair's own ``square()``**.

The load-bearing claims, in order of what they buy:

1. *Agreement* — on every probe of every planned pair, the grader-driven square
   returns the same verdict, divergence for divergence, as the pair's own
   ``square()``. Landing the authority changes no measured number.
2. *Authority* — a rigged ``square()`` cannot move the grader: not when it
   raises (it is never called), not when it lies ``ok=True`` over a defect the
   grader catches by itself.
3. *Non-vacuity* — the grader's own square really can fail, on both untrusted
   halves (a bad ``T`` and a bad ``Λ``).
4. *No silent fallback* — an unplanned pair is a typed abort, not a quiet
   deferral to the pair's square.
5. *Seam transparency*, and the honest pin on where it does not hold yet.
"""

import importlib
import pkgutil
import unittest

from gurdy.core import coverage, grader_square, pure_oracle, registry
from gurdy.core.errors import Unsupported
from gurdy.core.registry import Pair
from gurdy.core.types import AlignResult


def _import_all_pairs() -> None:
    import gurdy.pairs as pairs_pkg
    for mod in pkgutil.iter_modules(pairs_pkg.__path__):
        importlib.import_module(f"gurdy.pairs.{mod.name}")


class _RiggedSquare:
    """Context manager: replace a registered pair's ``square`` (the registry
    holds frozen Pairs, so swap the stored copy) and restore it."""

    def __init__(self, pair_id: str, square) -> None:
        self.pair_id, self.square = pair_id, square

    def __enter__(self) -> Pair:
        self.original = registry.get_pair(self.pair_id)
        registry._pairs[self.pair_id] = Pair(
            **{**self.original.__dict__, "square": self.square})
        return self.original

    def __exit__(self, *exc) -> None:
        registry._pairs[self.pair_id] = self.original


class TestAgreesWithPairSquare(unittest.TestCase):
    """Claim 1. The grader's authority is only worth having if it is also
    correct: same verdict as the pair's square on every probe, including the
    probes where both must abort ``Unsupported``."""

    @classmethod
    def setUpClass(cls) -> None:
        _import_all_pairs()

    def test_every_probe_of_every_planned_pair_agrees(self):
        checked = 0
        for pair_id in grader_square.planned_pairs():
            pair = registry.get_pair(pair_id)
            self.assertIsNotNone(pair.square, pair_id)
            for name, program in pair.probes.items():
                where = f"{pair_id}/{name}"
                try:
                    want = pair.square(program)
                except Unsupported:
                    # The trusted interpreter cannot run it either way; the
                    # grader must abort identically, not quietly count it.
                    with self.assertRaises(Unsupported, msg=where):
                        grader_square.grade(pair_id, program)
                    checked += 1
                    continue
                got = grader_square.grade(pair_id, program)
                self.assertEqual(bool(want.ok), bool(got.ok), where)
                self.assertEqual(repr(want.divergence), repr(got.divergence), where)
                checked += 1
        self.assertGreater(checked, 600, "the probe corpus shrank unexpectedly")

    def test_coverage_measures_the_same_set_through_either_route(self):
        # The number the gate actually reports (BENCHMARKS.md §2 conjunction).
        for pair_id in ("riscv-btor2", "evm-btor2", "smiles-formula"):
            pair = registry.get_pair(pair_id)
            via_pair = coverage.measure(pair.translator, pair.probes,
                                        faithful=pair.square)
            via_grader = coverage.measure(
                pair.translator, pair.probes,
                faithful=grader_square.faithful_for(pair_id))
            self.assertEqual(via_pair.covered, via_grader.covered, pair_id)
            self.assertEqual(via_pair.unfaithful, via_grader.unfaithful, pair_id)
            self.assertTrue(via_grader.conjoined)


class TestGraderIsAuthoritative(unittest.TestCase):
    """Claim 2. The whole point: what the pair says about itself is inert."""

    @classmethod
    def setUpClass(cls) -> None:
        _import_all_pairs()

    def test_pair_square_is_never_called(self):
        def boom(program):
            raise AssertionError("the grader called the pair's own square()")

        pair = registry.get_pair("riscv-btor2")
        name, program = next(iter(pair.probes.items()))
        with _RiggedSquare("riscv-btor2", boom):
            self.assertTrue(grader_square.grade("riscv-btor2", program).ok)

    def test_rigged_always_ok_square_does_not_hide_a_bad_lift(self):
        # The pair swears every probe is faithful; Λ is defective. The grader
        # must catch it anyway, because it never asks the pair.
        pair = registry.get_pair("riscv-btor2")
        name, program = next(iter(pair.probes.items()))
        real_lift = pair.target_to_source

        def bad_lift(trace):
            return [{**state, "pc": int(state.get("pc", 0)) + 1}
                    for state in real_lift(trace)]

        rigged = pure_oracle.InProcessOracle(pair.translator, bad_lift)
        with _RiggedSquare("riscv-btor2", lambda p: AlignResult(ok=True)) as original:
            self.assertTrue(registry.get_pair("riscv-btor2").square(program).ok)
            verdict = grader_square.grade("riscv-btor2", program, oracle=rigged)
        self.assertFalse(verdict.ok, "grader trusted the rigged square")
        self.assertEqual(verdict.divergence.field, "pc")
        # And the untouched pair still passes — the control is not always-fail.
        self.assertTrue(grader_square.grade("riscv-btor2", program).ok)

    def test_rigged_always_ok_square_does_not_hide_a_bad_translate(self):
        # The other untrusted half: a truncated artifact. Caught either as a
        # divergence or as an abort from the trusted interpreter — both are
        # "not a silent pass", which is what the control asserts.
        pair = registry.get_pair("riscv-btor2")
        name, program = next(iter(pair.probes.items()))
        real = pair.translator

        def truncating(p):
            art = bytes(real(p))
            return art[: max(1, len(art) // 2)]

        rigged = pure_oracle.InProcessOracle(truncating, pair.target_to_source)
        with _RiggedSquare("riscv-btor2", lambda p: AlignResult(ok=True)):
            try:
                verdict = grader_square.grade("riscv-btor2", program, oracle=rigged)
            except Exception as exc:
                self.assertNotIsInstance(exc, AssertionError)
            else:
                self.assertFalse(verdict.ok, "a truncated artifact passed")


class TestNoSilentFallback(unittest.TestCase):
    """Claim 4. An unplanned pair must be visibly unplanned."""

    @classmethod
    def setUpClass(cls) -> None:
        _import_all_pairs()

    def test_unplanned_pair_with_a_square_is_a_typed_abort(self):
        # btor2-havoc has a perfectly good square() — and no grader-side plan,
        # because its lax square runs along the pair's own witness embedding.
        pair = registry.get_pair("btor2-havoc")
        self.assertIsNotNone(pair.square)
        self.assertFalse(grader_square.has_plan("btor2-havoc"))
        program = next(iter(pair.probes.values()))
        with self.assertRaises(grader_square.NoPlan):
            grader_square.grade("btor2-havoc", program)
        with self.assertRaises(grader_square.NoPlan):
            grader_square.faithful_for("btor2-havoc")

    def test_planned_set_is_exactly_the_pairs_with_a_recipe(self):
        planned = set(grader_square.planned_pairs())
        with_square = {pid for pid, p in registry.list_pairs().items()
                       if p.square is not None}
        self.assertTrue(planned <= with_square, "a plan for a square-less pair")
        # The stated gap, so shrinking it is a deliberate, visible act.
        self.assertEqual(with_square - planned, {"btor2-havoc"})


class TestTheGateUsesIt(unittest.TestCase):
    """The capability is only authority once the gate actually grades through
    it — and says so per row, so a fallback is auditable."""

    @classmethod
    def setUpClass(cls) -> None:
        _import_all_pairs()
        import tools.pr_manifest as pr_manifest
        cls.pr_manifest = pr_manifest

    def test_planned_pair_row_is_graded_by_the_grader(self):
        pair = registry.get_pair("smiles-formula")
        row, error = self.pr_manifest._pair_row("smiles-formula", pair, touched=False)
        self.assertIsNone(error)
        self.assertEqual(row["graded_by"], "grader")
        self.assertIsNotNone(row["conjoined"])

    def test_unplanned_pair_row_declares_the_fallback(self):
        pair = registry.get_pair("btor2-havoc")
        row, error = self.pr_manifest._pair_row("btor2-havoc", pair, touched=False)
        self.assertIsNone(error)
        self.assertEqual(row["graded_by"], "pair-square")

    def test_square_less_pair_row_grades_by_nothing(self):
        pair = registry.get_pair("btor2-smtlib")     # predicted-grade, per-run
        row, error = self.pr_manifest._pair_row("btor2-smtlib", pair, touched=False)
        self.assertIsNone(error)
        self.assertIsNone(row["graded_by"])
        self.assertIsNone(row["conjoined"])


class TestSeamTransparency(unittest.TestCase):
    """Claim 5. The untrusted halves really do travel through the PureOracle —
    and the pin on the two pairs where the JSON channel is not yet faithful."""

    #: Every planned pair whose projected observables are JSON scalars.
    TRANSPARENT = tuple(p for p in grader_square.planned_pairs()
                        if p not in grader_square.CHANNEL_TUPLE_GAP)

    @classmethod
    def setUpClass(cls) -> None:
        _import_all_pairs()

    def test_verdicts_survive_the_out_of_process_backend(self):
        for pair_id in self.TRANSPARENT:
            pair = registry.get_pair(pair_id)
            with pure_oracle.for_pair(pair, "subprocess") as sub:
                checked = 0
                for name, program in list(pair.probes.items())[:6]:
                    try:
                        expected = grader_square.grade(pair_id, program)
                    except Unsupported:
                        continue
                    actual = grader_square.grade(pair_id, program, oracle=sub)
                    self.assertEqual(expected.ok, actual.ok, f"{pair_id}/{name}")
                    checked += 1
                self.assertGreater(checked, 0, pair_id)

    def test_gap_pairs_are_refused_out_of_process_not_answered_wrongly(self):
        for pair_id in grader_square.CHANNEL_TUPLE_GAP:
            program = next(iter(registry.get_pair(pair_id).probes.values()))
            with self.assertRaises(grader_square.ChannelGap):
                grader_square.grade(pair_id, program, backend="subprocess")
            # ...and in-process they are ordinary, passing squares.
            self.assertTrue(grader_square.grade(pair_id, program).ok)

    def test_the_gap_is_the_json_channel_widening_tuples(self):
        # Pins the actual cause, so the seam fix has an acceptance test and
        # this list cannot be shortened by accident. Note that
        # test_pure_oracle.TestLiftEquivalence cannot see this: it compares the
        # backends through json.dumps, which maps tuples to lists on BOTH sides.
        pair = registry.get_pair("wasm-btor2")
        program = next(iter(pair.probes.values()))
        inproc = pure_oracle.for_pair(pair, "inproc")
        artifact = inproc.translate(program)
        trace = pair.target_interpreter(artifact, {"steps": 4})
        with pure_oracle.for_pair(pair, "subprocess") as sub:
            here, there = inproc.lift(trace), sub.lift(trace)
        self.assertIsInstance(here[0]["stack"], tuple)
        self.assertIsInstance(there[0]["stack"], list)
        self.assertNotEqual(here, there)
        self.assertEqual(list(here[0]["stack"]), there[0]["stack"])


if __name__ == "__main__":
    unittest.main()
