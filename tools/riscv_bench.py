"""riscv-tests-derived reachability benchmark (BENCHMARKS.md §4; paper §6).

Turns the compliance slice (``tools/riscv_slice.py`` — self-checking programs
in the upstream riscv-tests HTIF ``tohost`` convention, built with the pinned
toolchain at the upstream link base 0x8000_0000) into a *question set with
machine-derived ground truth*:

1. Run each program in the shared reference interpreter (halting on the
   ``tohost`` write, exactly as the adequacy suite does).
2. For each data register the program exercises, derive two questions:
   a value the register held at some step (ground truth **reachable**) and a
   value no register held at any step (ground truth **unreachable** within
   the bound).
3. Decide every question independently along **both** RISC-V→SMT-LIB routes
   (direct and via the Sail model) with the bound covering the whole run.

Grading is two-axis: the routes must *agree* with each other (branch
corroboration, ROUTES.md §4) and each verdict must *match* the
interpreter-derived ground truth. A disagreement or mismatch localizes to a
program, register, and value. Every correct bounded-unreachable verdict is
additionally replay-corroborated: the strict BTOR2 interpreter runs the
direct route's system for the full bound and no ``bad`` may fire
(``corroborate_unreach`` — the paper's tested surrogate for Thm 4.9's
artifact-to-semantics hypothesis; recorded per question and in the totals).

The unreachable ground truth is bounded (BMC semantics): the value never
appears in the reference run, and the derivation excludes values any
register ever held, so the post-``tohost`` spin cannot introduce it.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gurdy.core import route as _route                       # noqa: E402
from gurdy.languages.riscv import load_elf                    # noqa: E402
from gurdy.languages.riscv.interp import run as _run          # noqa: E402

# Data registers the slice computes into (riscv-tests convention: gp/x3 is
# the case number, t0-t2 the operands/results). Address-valued registers
# (ra, sp, t5 base pointers) are deliberately excluded: the questions are
# about computed data, not link addresses.
_QUESTION_REGS = {3: "gp", 5: "t0", 6: "t1", 7: "t2"}
_K_MARGIN = 8


def derive_questions(elf_bytes: bytes, max_steps: int = 100_000) -> dict[str, Any]:
    """Reference-run one program and derive its question set."""
    image = load_elf(elf_bytes)
    binding = {"tohost": image.symbols["tohost"]} if "tohost" in image.symbols else {}
    trace = _run(image, binding, max_steps=max_steps)
    if not trace or not trace[-1].get("halted"):
        raise RuntimeError("program did not halt under the reference interpreter")

    # Every value any register held at any step: the exclusion set for
    # unreachable ground truth.
    held: set[int] = set()
    for row in trace:
        for r in range(1, 32):
            held.add(row[f"x{r}"])

    questions = []
    for reg, name in sorted(_QUESTION_REGS.items()):
        values = [row[f"x{reg}"] for row in trace]
        witness = next((v for v in reversed(values) if v != 0), None)
        if witness is None:
            continue                      # register unused by this program
        questions.append({"register": name, "reg": reg, "value": witness,
                          "expected": "REACHABLE"})
        absent = (0x1BAD_B002 + reg) & 0xFFFFFFFF
        while absent in held:
            absent += 1
        questions.append({"register": name, "reg": reg, "value": absent,
                          "expected": "UNREACHABLE"})
    return {"trace_len": len(trace), "k": len(trace) + _K_MARGIN,
            "questions": questions}


def _decide_z3(artifact: bytes):
    from gurdy.solvers.z3_smt import Z3SmtBackend
    return Z3SmtBackend().decide(artifact).verdict


def run_benchmark(elf_dir: str | Path, decide=None) -> dict[str, Any]:
    """Run the derived question set for every ELF in ``elf_dir`` along both
    RISC-V routes. Returns per-program rows and the summary counts."""
    # Registering the pairs is the caller's concern in tests; do it here so
    # the CLI/harvest path is self-contained.
    import gurdy.pairs.btor2_smtlib   # noqa: F401
    import gurdy.pairs.riscv_btor2    # noqa: F401
    import gurdy.pairs.riscv_sail     # noqa: F401
    import gurdy.pairs.sail_btor2     # noqa: F401

    decide = decide or _decide_z3
    routes = _route.routes("riscv", "smtlib")
    assert len(routes) == 2, routes

    from gurdy.languages.btor2 import corroborate_unreach

    programs = []
    totals = {"questions": 0, "agree": 0, "correct": 0,
              "unreach_replay_corroborated": 0, "unreach_total": 0}
    for elf in sorted(Path(elf_dir).iterdir()):
        if elf.suffix or not elf.is_file():
            continue                     # riscv-tests style: no extension
        elf_bytes = elf.read_bytes()
        derived = derive_questions(elf_bytes)
        rows = []
        t0 = time.perf_counter()
        for q in derived["questions"]:
            verdicts = {}
            for r in routes:
                head = {"image": load_elf(elf_bytes), "init_regs": {},
                        "property": {"reg_eq": [q["reg"], q["value"]]}}
                art = _route.run_route(r, head,
                                       {"btor2-smtlib": {"k": derived["k"]}})["artifact"]
                verdicts[" -> ".join(r)] = str(decide(art)).split(".")[-1]
            agree = len(set(verdicts.values())) == 1
            correct = agree and next(iter(set(verdicts.values()))) == q["expected"]
            row = {**q, "verdicts": verdicts, "agree": agree,
                   "correct": correct}
            if q["expected"] == "UNREACHABLE" and correct:
                # Tested surrogate for the solver-artifact-to-target-semantics
                # correspondence (paper Thm 4.9): the strict BTOR2 interpreter
                # replays the direct route's system k steps — no bad may fire.
                head = {"image": load_elf(elf_bytes), "init_regs": {},
                        "property": {"reg_eq": [q["reg"], q["value"]]}}
                btor = _route.run_route(["riscv-btor2"], head)["artifact"]
                row["replay_corroborated"] = corroborate_unreach(
                    btor, k=derived["k"])
                totals["unreach_total"] += 1
                totals["unreach_replay_corroborated"] += row["replay_corroborated"]
            rows.append(row)
            totals["questions"] += 1
            totals["agree"] += agree
            totals["correct"] += correct
        programs.append({"program": elf.name, "trace_len": derived["trace_len"],
                         "k": derived["k"], "questions": rows,
                         "time_s": round(time.perf_counter() - t0, 2)})
    return {"programs": programs, "totals": totals}


if __name__ == "__main__":
    import json
    import tempfile

    import riscv_slice

    target = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="riscv-bench-")
    riscv_slice.build(target)
    report = run_benchmark(target)
    print(json.dumps(report["totals"], indent=2))
    for p in report["programs"]:
        bad = [q for q in p["questions"] if not q["correct"]]
        print(f"{p['program']}: {len(p['questions'])} questions, "
              f"{sum(q['agree'] for q in p['questions'])} agree, "
              f"{sum(q['correct'] for q in p['questions'])} correct "
              f"({p['time_s']}s)" + (f"  BAD: {bad}" if bad else ""))
