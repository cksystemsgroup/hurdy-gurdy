"""Seeded fault injection: an escape-rate estimate for the gate (paper §6).

The bugs catalog (paper/results/bugs_caught.md) is mined from history and has
no denominator; the MUL/ADD blind spot proves the gate's escape rate is
nonzero. This harness measures it: inject seeded semantic mutations into the
``riscv-btor2`` translator's emissions and run each mutant through the
architecture's gates in the order the platform applies them:

1. **square** — the conjoined coverage suite (all 96 language-owned probes,
   square oracle per probe). A mutant whose artifact fails to parse or
   evaluate is caught here too (the strict evaluator, incident I1's layer).
2. **branch** — the standard solver-level questions decided along the
   mutated direct route vs. the intact Sail route (branch corroboration).
3. **bench** — the 78 compliance-derived ground-truth questions of
   tools/riscv_bench.py with the mutated route (needs the toolchain;
   skipped, and reported as skipped, when absent).

Mutants come in two families, mirroring the incident catalog:
- **uniform** rules model systematic mis-lowerings (every ``sext`` emitted
  as ``uext`` — incident I2's family),
- **site** rules model single-site defects (the k-th matching line only —
  incident I1's family).

A rule that changes no probe artifact is *inapplicable* and excluded from
the denominator. Operand swaps are only generated for non-commutative
operators, so survivors are not trivially-equivalent mutants; any survivor
is reported for manual audit. Deterministic: no randomness anywhere.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gurdy.core import oracle, registry, route as _route          # noqa: E402
from gurdy.core.errors import Unsupported                          # noqa: E402


# --- mutation rules over BTOR2 text -----------------------------------------

# Non-commutative ops where swapping the two operands is a semantic change.
_NONCOMMUTATIVE = ("sub", "sll", "srl", "sra", "ult", "ulte", "slt", "slte",
                   "concat")
_OP_SWAPS = [
    ("add", "sub"), ("sub", "add"), ("and", "or"), ("or", "and"),
    ("xor", "and"), ("sll", "srl"), ("srl", "sra"), ("sra", "srl"),
    ("ult", "ulte"), ("slt", "ult"), ("sext", "uext"), ("uext", "sext"),
    ("eq", "neq"), ("mul", "add"),
]


@dataclass(frozen=True)
class Mutation:
    name: str
    kind: str            # "op-swap" | "operand-swap" | "const-inc"
    op: str
    to: str | None = None
    site: int | None = None   # None => uniform; k => k-th matching line only

    def apply(self, text: str) -> tuple[str, int]:
        """Return (mutated text, number of lines changed)."""
        out, changed, seen = [], 0, 0
        for line in text.splitlines():
            toks = line.split()
            hit = len(toks) >= 2 and toks[1] == self.op
            if hit and (self.site is None or seen == self.site):
                if self.kind == "op-swap":
                    toks[1] = self.to
                elif self.kind == "operand-swap":
                    toks[-1], toks[-2] = toks[-2], toks[-1]
                elif self.kind == "const-inc":
                    toks[-1] = str(int(toks[-1]) + 1)
                changed += 1
                out.append(" ".join(toks))
            else:
                out.append(line)
            if hit:
                seen += 1
        return "\n".join(out) + "\n", changed


def mutation_set(sites: tuple[int, ...] = (0, 2, 5)) -> list[Mutation]:
    muts: list[Mutation] = []
    for a, b in _OP_SWAPS:
        muts.append(Mutation(f"uniform:{a}->{b}", "op-swap", a, b))
        for k in sites:
            muts.append(Mutation(f"site{k}:{a}->{b}", "op-swap", a, b, site=k))
    for op in _NONCOMMUTATIVE:
        muts.append(Mutation(f"uniform:swap-args:{op}", "operand-swap", op))
        for k in sites:
            muts.append(Mutation(f"site{k}:swap-args:{op}", "operand-swap",
                                 op, site=k))
    for k in sites:
        muts.append(Mutation(f"site{k}:constd+1", "const-inc", "constd",
                             site=k))
    return muts


# --- common-mode (both-leg) mutations ------------------------------------------

@dataclass(frozen=True)
class CommonMode:
    """One shared misreading applied to BOTH legs of the square: the reference
    interpreter and the riscv-btor2 translator mis-select the same construct
    the same way — the MUL/ADD incident's class, which single-leg mutation
    cannot model. Substitutions are exact, uniqueness-checked source strings
    applied to in-memory shadow copies of the two modules; the repository's
    code is never touched."""
    name: str
    construct: str
    interp_subst: tuple[tuple[str, str], ...]
    translate_subst: tuple[tuple[str, str], ...]


_CM: list[CommonMode] = [
    CommonMode(
        "mul-as-add", "MUL",
        (("        return (a * b) & m", "        return (a + b) & m"),),
        (('return b.op2("mul", w, a, c)', 'return b.op2("add", w, a, c)'),)),
    CommonMode(
        "sub-as-add", "SUB",
        (("w(a - b if alt else a + b)", "w(a + b)"),),
        (('val = b.op2("sub" if alt else "add", 64, a, c)',
          'val = b.op2("add", 64, a, c)'),)),
    CommonMode(
        "sra-as-srl", "SRA",
        (("w(_s64(a) >> (b & 0x3F) if alt else a >> (b & 0x3F))",
          "w(a >> (b & 0x3F))"),),
        (('val = b.op2("sra" if alt else "srl", 64, a, '
          'b.op2("and", 64, c, c64(0x3F)))',
          'val = b.op2("srl", 64, a, b.op2("and", 64, c, c64(0x3F)))'),)),
    CommonMode(
        "slt-as-sltu", "SLT",
        (("w(1 if _s64(a) < _s64(b) else 0)", "w(1 if a < b else 0)"),),
        (('val = b.uext(64, b.op2("slt", 1, a, c), 63)',
          'val = b.uext(64, b.op2("ult", 1, a, c), 63)'),)),
    CommonMode(
        "and-as-or", "AND",
        (("elif funct3 == 7:    # AND\n            w(a & b)",
          "elif funct3 == 7:    # AND\n            w(a | b)"),),
        (('elif funct3 == 7:  # AND\n            val = b.op2("and", 64, a, c)',
          'elif funct3 == 7:  # AND\n            val = b.op2("or", 64, a, c)'),)),
    CommonMode(
        "xor-as-and", "XOR",
        (("elif funct3 == 4:    # XOR\n            w(a ^ b)",
          "elif funct3 == 4:    # XOR\n            w(a & b)"),),
        (('elif funct3 == 4:  # XOR\n            val = b.op2("xor", 64, a, c)',
          'elif funct3 == 4:  # XOR\n            val = b.op2("and", 64, a, c)'),)),
]


def _shadow(base_mod: Any, subst: tuple, name: str) -> Any:
    """Exec a source-patched in-memory copy of ``base_mod``. Every
    substitution target must occur exactly once (a drifted source string is
    an error, not a silent no-op)."""
    import types
    src = Path(base_mod.__file__).read_text()
    for old, new in subst:
        n = src.count(old)
        if n != 1:
            raise RuntimeError(f"{name}: target occurs {n}x, not once: {old!r}")
        src = src.replace(old, new)
    mod = types.ModuleType(name)
    mod.__package__ = base_mod.__package__
    mod.__file__ = base_mod.__file__
    sys.modules[name] = mod
    exec(compile(src, base_mod.__file__, "exec"), mod.__dict__)
    return mod


def cm_modules(cm: CommonMode) -> tuple[Callable, Callable]:
    """(mutated interpreter run, mutated translator translate) for one
    common-mode misreading."""
    import importlib
    interp_mod = importlib.import_module("gurdy.languages.riscv.interp")
    translate_mod = importlib.import_module("gurdy.pairs.riscv_btor2.translate")
    mi = _shadow(interp_mod, cm.interp_subst, f"_cm_interp_{cm.name}")
    mt = _shadow(translate_mod, cm.translate_subst, f"_cm_translate_{cm.name}")
    return mi.run, mt.translate


# --- the gates, run against a mutated translator ------------------------------

def _mutant_translate(mutation: Mutation) -> Callable[[Any], bytes]:
    from gurdy.pairs.riscv_btor2 import translate

    def mutant(program: Any) -> bytes:
        text, _ = mutation.apply(translate(program).decode())
        return text.encode()

    return mutant


def _mutant_square(mutation: Mutation, program: dict[str, Any],
                   max_steps: int = 10_000):
    """riscv-btor2's square with the mutated artifact in the target leg."""
    from gurdy.pairs.riscv_btor2 import lift

    pair = registry.get_pair("riscv-btor2")
    image = program["image"]
    initial_mem = dict(image.mem)
    artifact = _mutant_translate(mutation)(program)
    src = list(pair.source_interpreter(image, {"regs": program.get("init_regs", {})},
                                       max_steps=max_steps))
    n = len(src)
    btrace = pair.target_interpreter(artifact,
                                     {"steps": n + 1, "state": {"mem": initial_mem}})
    carried = lift(btrace)
    return oracle.align(src, carried[1:n + 1], pair.projection)


def _applicable(mutation: Mutation, probes: dict[str, Any]) -> bool:
    from gurdy.pairs.riscv_btor2 import translate
    for program in probes.values():
        try:
            text = translate(program).decode()
        except Unsupported:
            continue
        if mutation.apply(text)[1]:
            return True
    return False


def _gate_square(mutation: Mutation, probes: dict[str, Any]) -> str | None:
    """Run the conjoined suite; return a catch description or None."""
    for name, program in probes.items():
        try:
            result = _mutant_square(mutation, program)
        except Unsupported:
            continue
        except Exception as exc:   # strict evaluator / parser rejection
            return f"evaluator: {type(exc).__name__} on {name}"
        if not result.ok:
            d = result.divergence
            return f"square: {name} step {d.step} {d.field}"
    return None


def _gate_branch(mutant_translate: Callable[[Any], bytes]) -> str | None:
    """The standard riscv solver questions, mutated direct vs intact Sail."""
    from gurdy.languages.riscv import asm
    from gurdy.languages.riscv.interp import image_from_words
    from gurdy.pairs.riscv_btor2 import lift
    from gurdy.solvers.z3_smt import Z3SmtBackend

    bridge = registry.get_pair("btor2-smtlib")
    questions = [
        ("const", [asm.addi(1, 0, 42), 0x73], {"reg_eq": [1, 42]}, 4),
        ("const99", [asm.addi(1, 0, 42), 0x73], {"reg_eq": [1, 99]}, 4),
        ("loop", [asm.addi(1, 0, 0), asm.addi(2, 0, 1), asm.addi(3, 0, 5),
                  asm.add(1, 1, 2), asm.addi(2, 2, 1), asm.bge(3, 2, -8),
                  0x73], {"reg_eq": [1, 15]}, 25),
        ("mem", [asm.addi(1, 0, 512), asm.addi(2, 0, 0x123),
                 asm.sw(2, 1, 0), asm.lw(3, 1, 0), 0x73],
         {"reg_eq": [3, 0x123]}, 10),
    ]
    for name, words, prop, k in questions:
        head = {"image": image_from_words(words), "init_regs": {},
                "property": prop}
        try:
            mutated = mutant_translate(head)
            direct = Z3SmtBackend().decide(
                bridge.translator({"system": mutated, "k": k})).verdict
            sail = Z3SmtBackend().decide(_route.run_route(
                ["riscv-sail", "sail-btor2", "btor2-smtlib"], head,
                {"btor2-smtlib": {"k": k}})["artifact"]).verdict
        except Exception as exc:
            return f"branch: {type(exc).__name__} on {name}"
        if direct != sail:
            return f"branch: disagree on {name} ({direct} vs {sail})"
    return None


def _load_riscv_bench():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "riscv_bench", ROOT / "tools" / "riscv_bench.py")
    riscv_bench = importlib.util.module_from_spec(spec)
    sys.modules["riscv_bench"] = riscv_bench
    spec.loader.exec_module(riscv_bench)
    return riscv_bench


def _gate_bench(mutant_translate: Callable[[Any], bytes],
                elf_dir: Path) -> str | None:
    """The compliance-derived questions with the mutated direct route."""
    riscv_bench = _load_riscv_bench()

    from gurdy.languages.riscv import load_elf
    from gurdy.solvers.z3_smt import Z3SmtBackend

    bridge = registry.get_pair("btor2-smtlib")
    for elf in sorted(Path(elf_dir).iterdir()):
        if elf.suffix or not elf.is_file():
            continue
        elf_bytes = elf.read_bytes()
        derived = riscv_bench.derive_questions(elf_bytes)
        for q in derived["questions"]:
            head = {"image": load_elf(elf_bytes), "init_regs": {},
                    "property": {"reg_eq": [q["reg"], q["value"]]}}
            try:
                mutated = mutant_translate(head)
                v = Z3SmtBackend().decide(bridge.translator(
                    {"system": mutated, "k": derived["k"]})).verdict
            except Exception as exc:
                return f"bench: {type(exc).__name__} on {elf.name}"
            if str(v).split(".")[-1] != q["expected"]:
                return (f"bench: {elf.name} {q['register']}=={q['value']:#x} "
                        f"expected {q['expected']} got {v}")
    return None


# --- the common-mode gates ------------------------------------------------------

def _cm_gate_square(run_fn: Callable, translate_fn: Callable) -> str | None:
    """The conjoined suite with BOTH legs mutated identically. The square is
    expected to be structurally blind here — a None return is the finding."""
    from gurdy.pairs.riscv_btor2 import lift

    pair = registry.get_pair("riscv-btor2")
    for name, program in pair.probes.items():
        image = program["image"]
        try:
            artifact = translate_fn(program)
            src = list(run_fn(image, {"regs": program.get("init_regs", {})},
                              max_steps=10_000))
            btrace = pair.target_interpreter(
                artifact, {"steps": len(src) + 1,
                           "state": {"mem": dict(image.mem)}})
            res = oracle.align(src, lift(btrace)[1:len(src) + 1],
                               pair.projection)
        except Unsupported:
            continue
        except Exception as exc:
            return f"square: {type(exc).__name__} on {name}"
        if not res.ok:
            d = res.divergence
            return f"square: {name} step {d.step} {d.field}"
    return None


def _cm_gate_bench(run_fn: Callable, translate_fn: Callable,
                   elf_dir: Path) -> tuple[str | None, bool]:
    """The compliance benchmark in the POISONED world: ground truth is
    derived by the MUTATED interpreter (the world where everyone shares the
    misreading), so expected-vs-direct grading is structurally blind — what
    can still catch the defect is the intact Sail route disagreeing with the
    mutated direct route. Returns (catch, poisoned_truth_stayed_blind)."""
    riscv_bench = _load_riscv_bench()
    riscv_bench._run = run_fn                      # poison the reference

    from gurdy.languages.riscv import load_elf
    from gurdy.solvers.z3_smt import Z3SmtBackend

    bridge = registry.get_pair("btor2-smtlib")
    poisoned_blind = True
    for elf in sorted(Path(elf_dir).iterdir()):
        if elf.suffix or not elf.is_file():
            continue
        elf_bytes = elf.read_bytes()
        try:
            derived = riscv_bench.derive_questions(elf_bytes)
        except Exception as exc:
            # The mutated world may not even halt its own programs; that is a
            # catch by the benchmark harness itself.
            return f"bench-branch: {type(exc).__name__} on {elf.name}", poisoned_blind
        for q in derived["questions"]:
            head = {"image": load_elf(elf_bytes), "init_regs": {},
                    "property": {"reg_eq": [q["reg"], q["value"]]}}
            try:
                direct = Z3SmtBackend().decide(bridge.translator(
                    {"system": translate_fn(head),
                     "k": derived["k"]})).verdict
                if str(direct).split(".")[-1] != q["expected"]:
                    poisoned_blind = False
                sail = Z3SmtBackend().decide(_route.run_route(
                    ["riscv-sail", "sail-btor2", "btor2-smtlib"], head,
                    {"btor2-smtlib": {"k": derived["k"]}})["artifact"]).verdict
            except Exception as exc:
                return (f"bench-branch: {type(exc).__name__} on {elf.name}",
                        poisoned_blind)
            if direct != sail:
                return (f"bench-branch: {elf.name} "
                        f"{q['register']}=={q['value']:#x} "
                        f"({direct} vs {sail})", poisoned_blind)
    return None, poisoned_blind


def _cm_gate_differential(run_fn: Callable, elf_dir: Path) -> str | None:
    """The external anchor: the mutated interpreter against the pinned
    Sail-generated emulator on the compliance ELFs (the adequacy campaign's
    own harness, with the mutant as subject)."""
    from gurdy.languages.riscv import load_elf
    from gurdy.languages.riscv.differential import (SailRiscvOracle,
                                                    differential,
                                                    executed_stream)
    if not SailRiscvOracle().available():
        return None                                # reported by the caller

    def subject(elf_bytes: bytes, max_steps: int):
        image = load_elf(elf_bytes)
        binding = ({"tohost": image.symbols["tohost"]}
                   if "tohost" in image.symbols else None)
        return executed_stream(run_fn(image, binding, max_steps=max_steps),
                               image.entry)

    for elf in sorted(Path(elf_dir).iterdir()):
        if elf.suffix or not elf.is_file():
            continue
        try:
            res = differential(elf.read_bytes(), subject=subject)
        except Exception as exc:
            return f"sail-differential: {type(exc).__name__} on {elf.name}"
        if not res.ok:
            d = res.divergence
            return f"sail-differential: {elf.name} step {d.step} {d.field}"
    return None


def run_common_mode(elf_dir: str | Path | None = None) -> dict[str, Any]:
    """The both-leg experiment (the class ``run_experiment`` cannot model):
    each common-mode misreading runs the gates in ring order — square
    (expected blind), authored branch questions, the benchmark in the
    poisoned world (cross-route disagreement is the catcher; expected-based
    grading is blind by construction), and the external Sail differential,
    which is also recorded as a parallel column for every mutant."""
    import gurdy.pairs.btor2_smtlib   # noqa: F401
    import gurdy.pairs.riscv_btor2    # noqa: F401
    import gurdy.pairs.riscv_sail     # noqa: F401
    import gurdy.pairs.sail_btor2     # noqa: F401

    rows = []
    counts = {"mutants": 0, "square_blind": 0, "branch": 0, "bench-branch": 0,
              "sail-differential": 0, "escaped": 0, "poisoned_truth_blind": 0}
    for cm in _CM:
        run_fn, translate_fn = cm_modules(cm)
        counts["mutants"] += 1
        t0 = time.perf_counter()
        caught = _cm_gate_square(run_fn, translate_fn)
        square_blind = caught is None
        counts["square_blind"] += square_blind
        if caught is None:
            caught = _gate_branch(translate_fn)
        poisoned_blind = None
        if caught is None and elf_dir is not None:
            caught, poisoned_blind = _cm_gate_bench(run_fn, translate_fn,
                                                    Path(elf_dir))
            counts["poisoned_truth_blind"] += bool(poisoned_blind)
        diff_catch = (_cm_gate_differential(run_fn, Path(elf_dir))
                      if elf_dir is not None else None)
        if caught is None and diff_catch:
            caught = diff_catch
        layer = caught.split(":")[0] if caught else "escaped"
        counts[layer] = counts.get(layer, 0) + 1
        rows.append({"mutation": cm.name, "construct": cm.construct,
                     "square_blind": square_blind,
                     "poisoned_truth_blind": poisoned_blind,
                     "sail_differential_catches": bool(diff_catch),
                     "caught_by": caught, "layer": layer,
                     "time_s": round(time.perf_counter() - t0, 2)})
        print(f"common-mode {cm.name:12s} -> {caught or 'ESCAPED'} "
              f"(square_blind={square_blind} diff={bool(diff_catch)})")
    return {"rows": rows, "counts": counts}


def run_experiment(elf_dir: str | Path | None = None,
                   sites: tuple[int, ...] = (0, 2, 5)) -> dict[str, Any]:
    import gurdy.pairs.btor2_smtlib   # noqa: F401
    import gurdy.pairs.riscv_btor2    # noqa: F401
    import gurdy.pairs.riscv_sail     # noqa: F401
    import gurdy.pairs.sail_btor2     # noqa: F401

    probes = registry.get_pair("riscv-btor2").probes
    rows = []
    counts = {"mutants": 0, "inapplicable": 0, "square": 0, "evaluator": 0,
              "branch": 0, "bench": 0, "escaped": 0}
    for mutation in mutation_set(sites):
        if not _applicable(mutation, probes):
            counts["inapplicable"] += 1
            continue
        counts["mutants"] += 1
        t0 = time.perf_counter()
        caught = _gate_square(mutation, probes)
        if caught is None:
            caught = _gate_branch(_mutant_translate(mutation))
        if caught is None and elf_dir is not None:
            caught = _gate_bench(_mutant_translate(mutation), Path(elf_dir))
        layer = caught.split(":")[0] if caught else "escaped"
        counts[layer] += 1
        rows.append({"mutation": mutation.name, "caught_by": caught,
                     "layer": layer,
                     "time_s": round(time.perf_counter() - t0, 2)})
        print(f"{mutation.name:28s} -> {caught or 'ESCAPED'}")
    return {"rows": rows, "counts": counts, "sites": list(sites),
            "bench_gate": elf_dir is not None}


if __name__ == "__main__":
    import json
    elf_dir = sys.argv[1] if len(sys.argv) > 1 else None
    out = sys.argv[2] if len(sys.argv) > 2 else None
    report = run_experiment(elf_dir)
    print(json.dumps(report["counts"], indent=2))
    if out:
        Path(out).write_text(json.dumps(report, indent=2))
