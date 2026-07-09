"""The specialization obligation (paper Thm 4.9(iv), `Specialization.lean`'s
``CommutesWithSpecialization``), discharged by SAMPLING rather than asserted
"by construction": translate the OPEN program once, then for sampled input
valuations x check two facts.

(1) **Translation commutes syntactically.** Attaching the valuation to the
    program does not change the emitted artifact (``T(specA x p) = T(p)``,
    byte for byte) — so specializing the artifact's input surface is
    genuinely a specialization of the ONE open translation the platform
    performs, exactly the shape ``universal_from_open_artifact`` needs.
(2) **The specialized instance is faithful.** The open artifact, with its
    free inputs bound to x, interpreted and carried back, aligns under the
    pair's projection with the source interpreter run at the same x.

Covered here: the two reasoning pairs whose encodings carry free inputs —
``ebpf-btor2`` (helper-call return streams become BTOR2 ``input`` nodes) and
``python-smtlib`` (integer function arguments become free ``Int`` symbols;
specialization is textual: conjoin ``(assert (= p__in c))``). The remaining
reasoning pairs' solver questions close their programs before translating
(deterministic systems), where the obligation is trivial.
"""

import random
import unittest

from gurdy.core import oracle, registry


def _z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


class TestEbpfSpecialization(unittest.TestCase):
    """ebpf-btor2: two helper calls (the proved-tier exhibits' shape), 25
    sampled helper-return streams against the single open artifact."""

    SAMPLES = 25

    def test_open_translation_commutes_with_helper_specialization(self):
        from gurdy.languages.ebpf import asm as e
        from gurdy.languages.ebpf.interp import program_from_words
        import gurdy.pairs.ebpf_btor2 as pb

        AND, ADD, MUL = 0x5, 0x0, 0x2
        words = [e.call(7), e.alu64_imm(AND, 0, 0xFFF),
                 e.alu64_imm(ADD, 0, 2), e.mov64_reg(6, 0),
                 e.call(7), e.alu64_imm(AND, 0, 0xFFF),
                 e.alu64_imm(ADD, 0, 2), e.alu64_reg(MUL, 6, 0), e.exit_()]
        prog = program_from_words(words)
        open_head = {"prog": prog, "init_regs": {}}
        artifact = pb.translate(open_head)          # the ONE open translation
        pair = registry.get_pair("ebpf-btor2")

        rng = random.Random(0xC0FFEE)               # deterministic samples
        for i in range(self.SAMPLES):
            stream = [{0: rng.getrandbits(64)} for _ in range(2)]
            # (1) the valuation does not change the emitted bytes.
            self.assertEqual(
                pb.translate(dict(open_head, helper_inputs=stream)), artifact,
                f"sample {i}: translation read the valuation")
            # (2) faithfulness at the specialized instance, from the single
            # open artifact (mirrors square()'s alignment, artifact hoisted).
            src = list(pair.source_interpreter(
                prog, {"regs": {}, "helper_inputs": [dict(d) for d in stream]}))
            n = len(src)
            binding = pb._call_input_binding(
                artifact, prog, src, [dict(d) for d in stream])
            btrace = pair.target_interpreter(
                artifact, {"steps": n + 1,
                           "state": {"mem": dict(prog.mem), "pkt": {}},
                           "inputs": binding})
            res = oracle.align(src, pb.lift(btrace)[1:n + 1], pair.projection)
            self.assertTrue(res.ok, (i, stream, res.divergence))


@unittest.skipUnless(_z3(), "z3 not installed")
class TestPythonSmtlibSpecialization(unittest.TestCase):
    """python-smtlib: the player experiment's assert-violability head; the
    open QF_LIA artifact specialized textually at sampled arguments must
    agree with the pinned CPython on whether the assert fires."""

    SRC = ("def f(x):\n"
           "    y = 0\n"
           "    for i in range(4):\n"
           "        if x > i:\n"
           "            y = y + x\n"
           "    assert y != 16\n")

    def test_open_translation_commutes_with_argument_specialization(self):
        from gurdy.languages.python.eval import run as py_run
        from gurdy.pairs.python_smtlib import translate
        from gurdy.pairs.python_smtlib.translate import load
        from gurdy.solvers.z3_smt import Z3SmtBackend
        from gurdy.core.solver import Verdict

        prog = load(self.SRC)
        artifact = translate(prog).decode()         # the ONE open translation
        self.assertIn("(declare-fun x__in () Int)", artifact)
        z3 = Z3SmtBackend()

        rng = random.Random(0xBEEF)
        samples = list(range(-3, 9)) + [rng.randint(-10**6, 10**6)
                                        for _ in range(8)]
        hits = 0
        for x0 in samples:
            # specZ: conjoin the input equation — a textual specialization of
            # the artifact, no re-translation.
            closed = artifact.replace(
                "(check-sat)", f"(assert (= x__in {x0}))\n(check-sat)")
            smt_violated = z3.decide(closed.encode()).verdict is Verdict.REACHABLE
            # specA: run the pinned CPython at the same argument.
            trace = py_run(prog, {"x": x0})
            py_violated = bool(trace and trace[-1].get("__violated__"))
            self.assertEqual(smt_violated, py_violated, f"x={x0}")
            hits += py_violated
        # The sample set must exercise both outcomes, or the test is vacuous.
        self.assertGreater(hits, 0)
        self.assertLess(hits, len(samples))


if __name__ == "__main__":
    unittest.main()
