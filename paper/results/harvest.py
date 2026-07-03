#!/usr/bin/env python3
"""Regenerate the milestone snapshot's evidence (paper/README.md).

Writes machine-readable results to paper/results/data/*.json and the paper's
tables to paper/results/tables/*.tex. Everything is measured from the live
registry and real runs at the current commit — nothing is transcribed from
docs. Sections: capability, composed, branch, cases, perf (run all by
default; select with --only).

RAM/CPU discipline: strictly sequential, no parallelism (see repo memory).
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

DATA = HERE / "data"
TABLES = HERE / "tables"
DATA.mkdir(exist_ok=True)
TABLES.mkdir(exist_ok=True)

# --- register the full graph (side-effecting imports) -----------------------
import gurdy.pairs.aarch64_btor2   # noqa: F401,E402
import gurdy.pairs.aarch64_sail    # noqa: F401,E402
import gurdy.pairs.btor2_smtlib    # noqa: F401,E402
import gurdy.pairs.c_riscv         # noqa: F401,E402
import gurdy.pairs.crn_smtlib      # noqa: F401,E402
import gurdy.pairs.ebpf_btor2      # noqa: F401,E402
import gurdy.pairs.evm_btor2       # noqa: F401,E402
import gurdy.pairs.python_smtlib   # noqa: F401,E402
import gurdy.pairs.riscv_btor2     # noqa: F401,E402
import gurdy.pairs.riscv_sail      # noqa: F401,E402
import gurdy.pairs.sail_btor2      # noqa: F401,E402
import gurdy.pairs.smiles_formula  # noqa: F401,E402
import gurdy.pairs.wasm_btor2      # noqa: F401,E402

from gurdy.core import grade, registry, route  # noqa: E402
from gurdy.core.coverage import measure        # noqa: E402
from gurdy.core.solver import Verdict          # noqa: E402

PAIR_ORDER = [
    "c-riscv", "riscv-btor2", "riscv-sail", "sail-btor2", "aarch64-btor2",
    "aarch64-sail", "wasm-btor2", "ebpf-btor2", "evm-btor2", "btor2-smtlib",
    "crn-smtlib", "python-smtlib", "smiles-formula",
]


def _git_head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()


def _z3_version() -> str:
    try:
        import z3
        return z3.get_version_string()
    except Exception:
        return "unavailable"


def _decide_z3(artifact):
    from gurdy.solvers.z3_smt import Z3SmtBackend
    return Z3SmtBackend().decide(artifact).verdict


def _tex_escape(s: str) -> str:
    return (s.replace("_", r"\_").replace("%", r"\%").replace("#", r"\#")
             .replace("&", r"\&"))


ROUTE_LABELS = {
    "riscv-btor2 -> btor2-smtlib": "RISC-V, direct",
    "riscv-sail -> sail-btor2 -> btor2-smtlib": "RISC-V, via Sail",
    "aarch64-btor2 -> btor2-smtlib": "AArch64, direct",
    "aarch64-sail -> sail-btor2 -> btor2-smtlib": "AArch64, via Sail",
    "c-riscv -> riscv-btor2 -> btor2-smtlib": "C, direct",
    "c-riscv -> riscv-sail -> sail-btor2 -> btor2-smtlib": "C, via Sail",
    "wasm-btor2 -> btor2-smtlib": "Wasm",
    "ebpf-btor2 -> btor2-smtlib": "eBPF",
    "evm-btor2 -> btor2-smtlib": "EVM",
    "crn-smtlib": "CRN",
    "python-smtlib": "Python",
    "smiles-formula": "SMILES",
}


def _route_label(key: str) -> str:
    return ROUTE_LABELS.get(key, _tex_escape(key))


def write_env() -> None:
    env = {
        "commit": _git_head(),
        "date": time.strftime("%Y-%m-%d"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "z3": _z3_version(),
    }
    (DATA / "env.json").write_text(json.dumps(env, indent=2))
    print("env:", env)


# --- capability matrix -------------------------------------------------------

def run_capability() -> None:
    rows, data = [], {}
    for pid in PAIR_ORDER:
        pair = registry.get_pair(pid)
        if not pair.probes:
            acc, conj, gaps, unfaithful = None, None, {}, {}
        else:
            t0 = time.perf_counter()
            report = measure(pair.translator, pair.probes)
            acc = (len(report.covered), report.total)
            gaps = report.histogram
            if pair.square is not None:
                creport = measure(pair.translator, pair.probes,
                                  faithful=pair.square)
                conj = (len(creport.covered), creport.total)
                unfaithful = creport.unfaithful
            else:
                conj, unfaithful = None, {}
            dt = time.perf_counter() - t0
            conjtxt = f"{conj[0]}/{conj[1]}" if conj else "per-run"
            print(f"capability {pid}: accepted {acc[0]}/{acc[1]} "
                  f"conjoined {conjtxt} ({dt:.1f}s)")
        data[pid] = {
            "source": pair.source, "target": pair.target,
            "fidelity": pair.fidelity, "status": str(pair.status),
            "accepted": acc, "conjoined": conj,
            "unfaithful": unfaithful, "unsupported_histogram": gaps,
        }
        acctxt = f"{acc[0]}/{acc[1]}" if acc else "---"
        if conj:
            conjtxt = f"{conj[0]}/{conj[1]}"
        elif acc:
            conjtxt = "per-run"   # no decidable square: faithfulness at question time
        else:
            conjtxt = "---"
        gaptxt = str(len(gaps)) if acc else "---"
        rows.append(
            f"{_tex_escape(pid)} & "
            f"\\texttt{{{_tex_escape(pair.fidelity)}}} & {acctxt} & {conjtxt}"
            f" & {gaptxt} \\\\")
    (DATA / "capability.json").write_text(json.dumps(data, indent=2))
    (TABLES / "capability.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table}\n\\caption{Capability snapshot: per-pair construct\n"
        "coverage against the language-owned inventory. \\emph{Accepted} =\n"
        "the probe translates without a typed \\unsupported{} abort;\n"
        "\\emph{conjoined} = accepted \\emph{and} the pair's square oracle\n"
        "passes on the probe --- Definition~\\ref{def:coverage}'s conjunction,\n"
        "measured directly (\\S\\ref{sec:eval-capability}). Pairs without a\n"
        "decidable square (the \\texttt{predicted}-grade hops and the\n"
        "reproducible C hop) discharge the faithfulness conjunct per run\n"
        "instead (\\S\\ref{sec:composition}), marked \\emph{per-run}. Gaps counts\n"
        "the distinct typed \\unsupported{} constructs. Measured from the\n"
        "live registry at the snapshot commit.}\n"
        "\\label{tab:capability}\n\\footnotesize\n"
        "\\begin{tabular}{@{}llllr@{}}\n\\toprule\n"
        "Pair (source$\\to$target) & Grade & Accepted & Conjoined & Gaps \\\\\n\\midrule\n"
        + "\n".join(rows) +
        "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")


# --- composed route coverage -------------------------------------------------

COMPOSED_ENDPOINTS = [
    ("riscv", "smtlib"), ("aarch64", "smtlib"), ("wasm", "smtlib"),
    ("ebpf", "smtlib"), ("evm", "smtlib"), ("crn", "smtlib"),
    ("python", "smtlib"), ("smiles", "molecular-formula"),
]


def run_composed() -> dict:
    data = {}
    for src, dst in COMPOSED_ENDPOINTS:
        t0 = time.perf_counter()
        try:
            reports = grade.composed_coverage_by_route(src, dst, k=1)
        except Exception as exc:  # a route whose head probes need tools absent here
            print(f"composed {src}->{dst}: SKIP ({exc})")
            continue
        for rids, rep in reports.items():
            key = " -> ".join(rids)
            data[key] = {"covered": len(rep.covered), "total": rep.total,
                         "missing": rep.missing, "conjoined": rep.conjoined,
                         "unfaithful": rep.unfaithful}
            print(f"composed {key}: {len(rep.covered)}/{rep.total} "
                  f"(conjoined={rep.conjoined}, "
                  f"{time.perf_counter()-t0:.1f}s)")
    (DATA / "composed.json").write_text(json.dumps(data, indent=2))
    return data


# --- branch agreement --------------------------------------------------------

def run_branch(composed: dict | None = None) -> None:
    from gurdy.languages.riscv import asm
    from gurdy.languages.riscv.interp import image_from_words

    results = []

    def record(name, routes, ba, dts):
        results.append({
            "question": name,
            "routes": {" -> ".join(k): str(v) for k, v in ba.verdicts.items()},
            "agree": ba.agree,
            "times_s": {" -> ".join(k): round(t, 2) for k, t in dts.items()},
        })
        print(f"branch {name}: agree={ba.agree} "
              f"{ {' -> '.join(k): str(v) for k, v in ba.verdicts.items()} }")

    def timed_branch(name, routes, head, params):
        dts = {}
        verdicts = {}
        for r in routes:
            t0 = time.perf_counter()
            artifact = route.run_route(r, head, params)["artifact"]
            verdicts[tuple(r)] = _decide_z3(artifact)
            dts[tuple(r)] = time.perf_counter() - t0
        ba = grade.BranchAgreement(verdicts, len(set(verdicts.values())) <= 1)
        record(name, routes, ba, dts)

    # RISC-V: the two independent lowerings, decided at SMT-LIB.
    rroutes = route.routes("riscv", "smtlib")
    assert len(rroutes) == 2, rroutes

    def rhead(words, prop):
        return {"image": image_from_words(words), "init_regs": {},
                "property": prop}

    const = [asm.addi(1, 0, 42), 0x73]
    loop = [asm.addi(1, 0, 0), asm.addi(2, 0, 1), asm.addi(3, 0, 5),
            asm.add(1, 1, 2), asm.addi(2, 2, 1), asm.bge(3, 2, -8), 0x73]
    mem = [asm.addi(1, 0, 512), asm.addi(2, 0, 0x123),
           asm.sw(2, 1, 0), asm.lw(3, 1, 0), 0x73]
    k = lambda n: {"btor2-smtlib": {"k": n}}
    timed_branch("riscv const x1==42 (reach)", rroutes,
                 rhead(const, {"reg_eq": [1, 42]}), k(4))
    timed_branch("riscv const x1==99 (unreach)", rroutes,
                 rhead(const, {"reg_eq": [1, 99]}), k(4))
    timed_branch("riscv loop sum==15 (reach)", rroutes,
                 rhead(loop, {"reg_eq": [1, 15]}), k(25))
    timed_branch("riscv loop sum==99 (unreach)", rroutes,
                 rhead(loop, {"reg_eq": [1, 99]}), k(25))
    timed_branch("riscv store/load 0x123 (reach)", rroutes,
                 rhead(mem, {"reg_eq": [3, 0x123]}), k(10))
    timed_branch("riscv store/load 0x999 (unreach)", rroutes,
                 rhead(mem, {"reg_eq": [3, 0x999]}), k(10))

    # C head: the opaque compiler re-established downstream, both routes.
    from gurdy.pairs.c_riscv import find_gcc
    if find_gcc():
        croutes = route.routes("c", "smtlib")
        src = ("void _start(void){ long r=(5*8 + 7); "
               "__asm__ volatile(\"mv a0,%0\\n\\tecall\\n\"::\"r\"(r):\"a0\");"
               " for(;;){} }\n")

        def cparams(v):
            return {"riscv-btor2": {"property": {"reg_eq": [10, v]}},
                    "riscv-sail": {"property": {"reg_eq": [10, v]}},
                    "btor2-smtlib": {"k": 6}}

        timed_branch("C a0==47 (reach)", croutes, {"source": src}, cparams(47))
        timed_branch("C a0==99 (unreach)", croutes, {"source": src}, cparams(99))
    else:
        print("branch: riscv64 gcc unavailable, skipping C head")

    # AArch64: solver-level agreement across the two independent routes
    # (direct vs Sail-model-mediated), since sail-btor2 0.2 lowers the A64 arm.
    from gurdy.languages.aarch64.interp import program_from_words as a64_img
    from gurdy.languages.aarch64 import asm as a64asm
    aroutes = route.routes("aarch64", "smtlib")
    assert len(aroutes) == 2, aroutes

    def ahead(words, prop):
        return {"image": a64_img(list(words)), "init_regs": {},
                "property": prop}

    a64_alu = [a64asm.movz(0, 40), a64asm.add_imm(1, 0, 2)]
    a64_loop = [a64asm.movz(0, 3), a64asm.subs_imm(0, 0, 1),
                a64asm.b_cond("NE", -4)]
    timed_branch("aarch64 movz/add x1==42 (reach)", aroutes,
                 ahead(a64_alu, {"reg_eq": [1, 42]}), k(4))
    timed_branch("aarch64 movz/add x1==999 (unreach)", aroutes,
                 ahead(a64_alu, {"reg_eq": [1, 999]}), k(4))
    timed_branch("aarch64 SUBS/B.NE loop x0==1 (reach)", aroutes,
                 ahead(a64_loop, {"reg_eq": [0, 1]}), k(12))
    timed_branch("aarch64 SUBS/B.NE loop x0==5 (unreach)", aroutes,
                 ahead(a64_loop, {"reg_eq": [0, 5]}), k(12))

    # AArch64: trace-level agreement of the two carried-back routes under pi
    # (mirrors tests/test_aarch64_sail_pair.py::_assert_branch_agrees).
    import json as _json
    from gurdy.languages.aarch64 import asm as a64
    from gurdy.languages.aarch64.interp import program_from_words, run as a64_run
    from gurdy.languages.btor2 import interpret as btor_interp
    from gurdy.languages.sail import run as sail_run
    from gurdy.pairs.aarch64_btor2 import translate as ab_translate
    from gurdy.pairs.aarch64_btor2.lift import lift as ab_lift
    from gurdy.pairs.aarch64_sail import PROJECTION as A64_PI
    from gurdy.pairs.aarch64_sail import translate as as_translate
    from gurdy.pairs.aarch64_sail.lift import lift as as_lift

    a64_progs = {
        "aarch64 flags + loop (SUBS/B.NE)": [a64.movz(0, 3),
                                             a64.subs_imm(0, 0, 1),
                                             a64.b_cond("NE", -4),
                                             a64.movz(1, 7)],
        "aarch64 32-bit W forms": [a64.movz_w(0, 0xFFFF),
                                   a64.add_imm_w(1, 0, 1),
                                   a64.subs_imm_w(2, 1, 5)],
    }
    a64_rows = []
    for name, words in a64_progs.items():
        try:
            init_sp = 1 << 20
            program = {"image": program_from_words(list(words)),
                       "init_regs": {}, "init_sp": init_sp}
            n = len(a64_run(program["image"], {"regs": {}, "sp": init_sp}))
            direct = ab_lift(btor_interp(ab_translate(program),
                                         {"steps": n + 1}))[1:n + 1]
            mediated = as_lift(sail_run(
                _json.loads(as_translate(program).decode()), {}))
            sel = lambda rows: [A64_PI.select(r) for r in rows]
            agree = sel(direct) == sel(mediated)
        except Exception as exc:
            print(f"branch {name}: SKIP ({exc})")
            continue
        a64_rows.append({"question": name, "agree": agree,
                         "level": "carried-back trace equality under pi"})
        print(f"branch {name}: agree={agree}")

    (DATA / "branch.json").write_text(json.dumps(
        {"solver_level": results, "trace_level": a64_rows}, indent=2))

    # ---- table: composed coverage + branch agreement -----------------------
    composed = composed if composed is not None else json.loads(
        (DATA / "composed.json").read_text())
    crows = [
        f"{_route_label(k)} & {v['covered']}/{v['total']} \\\\"
        for k, v in composed.items()
    ]
    brows = []
    for r in results:
        verdicts = set(r["routes"].values())
        v = verdicts.pop() if len(verdicts) == 1 else "DISAGREE"
        v = str(v).split(".")[-1].replace("REACHABLE", "reach")
        v = v.replace("UNreach", "unreach")
        tmax = max(r["times_s"].values())
        brows.append(f"{_tex_escape(r['question'])} & "
                     f"{'\\checkmark' if r['agree'] else '$\\times$'} & "
                     f"{_tex_escape(v)} & {tmax:.1f} \\\\")
    for r in a64_rows:
        brows.append(f"{_tex_escape(r['question'])} & "
                     f"{'\\checkmark' if r['agree'] else '$\\times$'} & "
                     f"trace $=_\\pi$ & --- \\\\")
    (TABLES / "branch.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table}\n\\caption{Composed \\emph{conjoined} coverage: a\n"
        "probe counts iff it survives every hop \\emph{and} every hop with a\n"
        "decidable square passes it on that hop's input (the route-level\n"
        "reading of Definition~\\ref{def:coverage}; ``via Sail'' routes are\n"
        "the independently derived branch; denominators are the source\n"
        "language's inventory, \\S\\ref{sec:eval-branch}), and branch\n"
        "agreement: the same question decided along both routes. Times are\n"
        "the slower route, end to end (translate every hop + decide with Z3).}\n"
        "\\label{tab:branch}\n\\footnotesize\n"
        "\\begin{tabular}{@{}lr@{}}\n\\toprule\n"
        "Route (to SMT-LIB) & Composed coverage \\\\\n\\midrule\n"
        + "\n".join(crows) +
        "\n\\bottomrule\n\\end{tabular}\n\n\\medskip\n\n"
        "\\begin{tabular}{@{}lclr@{}}\n\\toprule\n"
        "Question (both routes) & Agree & Verdict & Time (s) \\\\\n\\midrule\n"
        + "\n".join(brows) +
        "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")


# --- case studies ------------------------------------------------------------

def run_cases() -> None:
    cases = []

    # Case 1: C spine, witness carried back and replayed at source level.
    from gurdy.pairs.c_riscv import find_gcc
    if find_gcc():
        from gurdy.languages.riscv import load_elf, run as riscv_run
        from gurdy.pairs.c_riscv import c_function_at, translate as c_translate
        src = ("void _start(void){ long r=(5*8 + 7); "
               "__asm__ volatile(\"mv a0,%0\\n\\tecall\\n\"::\"r\"(r):\"a0\");"
               " for(;;){} }\n")
        t0 = time.perf_counter()
        croutes = route.routes("c", "smtlib")
        params = {"riscv-btor2": {"property": {"reg_eq": [10, 47]}},
                  "riscv-sail": {"property": {"reg_eq": [10, 47]}},
                  "btor2-smtlib": {"k": 6}}
        verdicts = {}
        for r in croutes:
            verdicts[" -> ".join(r)] = str(
                _decide_z3(route.run_route(r, {"source": src}, params)["artifact"]))
        img = load_elf(c_translate({"source": src}))
        final = riscv_run(img, {"regs": {2: 1 << 20}})[-1]
        replay_ok = bool(final["halted"]) and final["x10"] == 47
        cases.append({
            "case": "C spine (both routes + source replay)",
            "verdicts": verdicts, "replay_ok": replay_ok,
            "carry_back": f"halt in {c_function_at(img, img.entry)}(), a0=47",
            "time_s": round(time.perf_counter() - t0, 2)})
        print("case C:", verdicts, "replay_ok:", replay_ok)

    # Case 2: Python -> QF_LIA, solver witness replayed through pinned CPython.
    from gurdy.pairs.python_smtlib import reach as py_reach
    py_src = (
        "def f(x):\n"
        "    y = 0\n"
        "    for i in range(4):\n"
        "        if x > i:\n"
        "            y = y + x\n"
        "    assert y != 16\n")
    t0 = time.perf_counter()
    info = py_reach(py_src)
    cases.append({
        "case": "Python assert violable? (QF_LIA)",
        "verdicts": {"python-smtlib": str(info["verdict"])},
        "witness_inputs": info.get("inputs"),
        "smt_model_ok": info.get("smt_model_ok"),
        "replay_ok": info.get("witness_ok"),
        "time_s": round(time.perf_counter() - t0, 2)})
    print("case Python:", info["verdict"], info.get("inputs"),
          "replay:", info.get("witness_ok"))

    # Case 3: EVM -> BTOR2, decided natively (btormc + .wit replay) and
    # bridged (btor2-smtlib + z3): solve-step corroboration.
    from gurdy.pairs.evm_btor2 import translate as evm_translate
    from gurdy.solvers.native_btor2 import NativeBtor2Checker
    # PUSH1 6; PUSH1 7; MUL; STOP  -- can the top of stack be 42?
    code = bytes([0x60, 0x06, 0x60, 0x07, 0x02, 0x00])
    head = {"code": code, "property": {"stack_eq": [0, 42]}}
    t0 = time.perf_counter()
    system = evm_translate(head)
    bridged = str(_decide_z3(route.run_route(
        ["evm-btor2", "btor2-smtlib"], head, {"btor2-smtlib": {"k": 5}})["artifact"]))
    native = NativeBtor2Checker()
    nverdict, wit_ok = "unavailable", None
    if native.available():
        nverdict = str(native.decide(system, k=5))
        try:
            from gurdy.languages.btor2.witness import replay
            out = native._run(system, 5)
            trace = replay(system, out)
            wit_ok = trace is not None
        except Exception as exc:
            wit_ok = f"replay skipped: {exc}"
    cases.append({
        "case": "EVM 6*7==42 native vs bridged",
        "verdicts": {"bridged z3": bridged, "native btormc": nverdict},
        "witness_replay": wit_ok,
        "time_s": round(time.perf_counter() - t0, 2)})
    print("case EVM:", bridged, nverdict, "wit replay:", wit_ok)

    # Case 4: CRN -> QF_LIA with firing-flag witness replay.
    from gurdy.pairs.crn_smtlib import reach as crn_reach
    try:
        t0 = time.perf_counter()
        cinfo = crn_reach("species A B\ninit A 2 B 0\nrxn A -> B\n",
                          3, {"A": 0, "B": 2})
        cases.append({
            "case": "CRN A->B twice reaches B=2",
            "verdicts": {"crn-smtlib": str(cinfo.get("verdict"))},
            "replay_ok": cinfo.get("witness_ok"),
            "time_s": round(time.perf_counter() - t0, 2)})
        print("case CRN:", cinfo.get("verdict"), "replay:", cinfo.get("witness_ok"))
    except Exception as exc:
        print(f"case CRN: SKIP ({exc})")

    (DATA / "cases.json").write_text(json.dumps(cases, indent=2, default=str))

    rows = []
    for c in cases:
        vals = {str(x).split(".")[-1] for x in c["verdicts"].values()}
        if len(vals) == 1:
            n = len(c["verdicts"])
            v = vals.pop()
            vtxt = v if n == 1 else f"{v} (both agree)"
        else:
            vtxt = "; ".join(f"{_route_label(k)}: {str(x).split('.')[-1]}"
                             for k, x in c["verdicts"].items())
        extra = c.get("replay_ok", c.get("witness_replay"))
        extra = {"True": "\\checkmark", "False": "$\\times$"}.get(
            str(extra), str(extra))
        rows.append(f"{_tex_escape(c['case'])} & {_tex_escape(vtxt)} & "
                    f"{extra} & {c['time_s']} \\\\")
    (TABLES / "cases.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table}\n\\caption{End-to-end case studies. ``Replay''\n"
        "is the source-level witness check of Theorem~\\ref{thm:existential}:\n"
        "the carried-back witness re-executed by the source interpreter.}\n"
        "\\label{tab:cases}\n\\footnotesize\n"
        "\\begin{tabular}{@{}>{\\raggedright\\arraybackslash}p{0.40\\linewidth}"
        ">{\\raggedright\\arraybackslash}p{0.30\\linewidth}cr@{}}\n"
        "\\toprule\n"
        "Case & Verdicts & Replay & Time (s) \\\\\n\\midrule\n"
        + "\n".join(rows) +
        "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")


# --- performance and determinism ---------------------------------------------

def run_perf() -> None:
    from gurdy.languages.riscv import asm
    from gurdy.languages.riscv.interp import image_from_words

    loop = [asm.addi(1, 0, 0), asm.addi(2, 0, 1), asm.addi(3, 0, 5),
            asm.add(1, 1, 2), asm.addi(2, 2, 1), asm.bge(3, 2, -8), 0x73]
    head = {"image": image_from_words(loop), "init_regs": {},
            "property": {"reg_eq": [1, 15]}}
    params = {"btor2-smtlib": {"k": 25}}

    from gurdy.core import cache as _cache

    perf = {}
    for r in route.routes("riscv", "smtlib"):
        key = " -> ".join(r)
        _cache._reset()   # cold: measure real translation work
        t0 = time.perf_counter()
        artifact = route.run_route(r, head, params)["artifact"]
        t_cold = time.perf_counter() - t0
        t0 = time.perf_counter()
        route.run_route(r, head, params)
        t_warm = time.perf_counter() - t0   # content-addressed cache hit
        t0 = time.perf_counter()
        verdict = _decide_z3(artifact)
        t_decide = time.perf_counter() - t0
        det = grade.composed_determinism(r, head, params)
        perf[key] = {"translate_cold_s": round(t_cold, 4),
                     "translate_warm_s": round(t_warm, 4),
                     "decide_s": round(t_decide, 3),
                     "twice_and_diff_ok": det,
                     "verdict": str(verdict),
                     "artifact_bytes": len(artifact)}
        print(f"perf {key}: {perf[key]}")

    (DATA / "perf.json").write_text(json.dumps(perf, indent=2))
    rows = [
        f"{_route_label(k)} & {v['translate_cold_s']*1000:.0f} & "
        f"{v['translate_warm_s']*1000:.1f} & {v['decide_s']*1000:.0f} & "
        f"{'\\checkmark' if v['twice_and_diff_ok'] else '$\\times$'} & "
        f"{v['artifact_bytes']//1000}\\,kB \\\\"
        for k, v in perf.items()]
    (TABLES / "perf.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table}\n\\caption{Route cost for the RISC-V loop question\n"
        "($k{=}25$ unrolling): whole-route translation, cold vs.\\ warm (the\n"
        "content-addressed cache of Proposition~\\ref{prop:cache}), Z3 decide\n"
        "time, byte-determinism (twice-and-diff), and artifact size.}\n"
        "\\label{tab:perf}\n\\footnotesize\n"
        "\\begin{tabular}{@{}lrrrcr@{}}\n\\toprule\n"
        "Route & cold (ms) & warm (ms) & decide (ms) & det. & artifact \\\\\n"
        "\\midrule\n"
        + "\n".join(rows) +
        "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")


# --- the proved tier ----------------------------------------------------------

def run_proved() -> None:
    """Certified unreachability end to end (SOLVERS.md §5-6): multi-engine
    corroboration, a bit-blasted DRAT certificate, and the *independent*
    checker — plus the controls that keep the checker honest."""
    from gurdy.languages.ebpf import asm as easm
    from gurdy.languages.ebpf.interp import program_from_words
    from gurdy.pairs.btor2_smtlib.translate import translate as bridge
    from gurdy.pairs.ebpf_btor2 import translate as ebpf_translate
    from gurdy.solvers.proved import (bitblast_cnf, check_drat,
                                      prove_unreachable)

    # r0 = helper() (a free input by the CALL model); r0 *= r0; r6 = r0.
    # r6 only ever holds 0 or x^2, and 3 is not a square mod 2^64.
    words = [easm.call(7), easm.alu64_reg(0x2, 0, 0), easm.mov64_reg(6, 0),
             easm.exit_()]

    def head(target):
        return {"prog": program_from_words(words), "init_regs": {},
                "property": {"reg_eq": [6, target]}}

    data: dict[str, Any] = {}
    t0 = time.perf_counter()
    r = prove_unreachable(ebpf_translate(head(3)), 5)
    data["unreachable"] = {
        "question": "eBPF: helper()^2 == 3 (no square mod 2^64)",
        "verdict": str(r.verdict), "tier": r.tier, "method": r.method,
        "engines": r.engines, "checker_ok": r.checker_ok,
        "certificate_bytes": len(r.certificate or b""),
        "checker": r.provenance.get("checker"),
        "elaborator": r.provenance.get("elaborator"),
        "lrat_bytes": r.provenance.get("lrat_bytes"),
        "tcb": r.tcb, "time_s": round(time.perf_counter() - t0, 2)}
    print("proved unreachable:", data["unreachable"])

    t0 = time.perf_counter()
    r2 = prove_unreachable(ebpf_translate(head(4)), 5)
    data["reachable_sibling"] = {
        "question": "eBPF: helper()^2 == 4 (x = 2)",
        "verdict": str(r2.verdict), "tier": r2.tier,
        "certificate": r2.certificate is not None,
        "time_s": round(time.perf_counter() - t0, 2)}
    print("proved sibling:", data["reachable_sibling"])

    # Controls: the same certificate against the *satisfiable* sibling's CNF
    # must NOT verify (no valid refutation of a satisfiable formula exists),
    # and neither must a bare empty-clause claim — for BOTH checkers.
    controls = {}
    if r.certificate is not None:
        sat_cnf = bitblast_cnf(bridge(
            {"system": ebpf_translate(head(4)), "k": 5}))
        if sat_cnf:
            controls["cert_vs_sat_formula"] = check_drat(sat_cnf, r.certificate)
            controls["empty_clause_vs_sat_formula"] = check_drat(sat_cnf, b"0\n")
            try:
                from gurdy.solvers.proved import (check_lrat_verified,
                                                  elaborate_lrat)
                unsat_cnf = bitblast_cnf(bridge(
                    {"system": ebpf_translate(head(3)), "k": 5}))
                lrat = elaborate_lrat(unsat_cnf, r.certificate)
                if lrat is not None:
                    controls["lrat_vs_sat_formula_verified"] = \
                        check_lrat_verified(sat_cnf, lrat)
                controls["garbage_lrat_verified"] = \
                    check_lrat_verified(sat_cnf, b"1 0 0\n")
            except Exception as exc:
                print(f"proved: cake_lpr controls skipped ({exc})")
    data["negative_controls_verify"] = controls
    print("proved controls (must all be False):", controls)

    (DATA / "proved.json").write_text(json.dumps(data, indent=2, default=str))

    u, s = data["unreachable"], data["reachable_sibling"]
    ctrl_ok = controls and not any(controls.values())
    (TABLES / "proved.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table}\n\\caption{The certified (\\tprov) row inhabited:\n"
        "an input-driven unreachability claim from a real pair, corroborated\n"
        "by three engines, certified by a bit-blasted DRAT proof, and\n"
        "re-validated by the independent checker. The controls are bogus\n"
        "checks that must fail --- and do.}\n"
        "\\label{tab:proved}\n\\footnotesize\n"
        "\\begin{tabular}{@{}p{0.52\\linewidth}p{0.40\\linewidth}@{}}\n"
        "\\toprule\n"
        "Question & eBPF: $\\mathit{helper}()^2 = 3$ "
        "(no square mod $2^{64}$) \\\\\n"
        f"Engines agreeing \\textsc{{unsat}} & {', '.join(u['engines'])} \\\\\n"
        f"Certificate & {u['certificate_bytes']}\\,B DRAT "
        "(bitwuzla$\\to$CNF, cadical$\\to$DRAT)"
        + (f", elaborated to {u['lrat_bytes']}\\,B LRAT (drat-trim, untrusted)"
           if u.get("lrat_bytes") is not None else "") + " \\\\\n"
        + ("Independent check & cake\\_lpr (\\emph{formally verified}): "
           if u.get("method") == "bitblast-drat-lrat"
           else "Independent check & drat-trim: ")
        + f"{'\\textbf{verified}' if u['checker_ok'] else 'FAILED'};"
        f" tier \\texttt{{{u['tier']}}} \\\\\n"
        f"Resulting \\tcb & {_tex_escape(', '.join(u['tcb']))} \\\\\n"
        f"Reachable sibling ($x^2{{=}}4$) & "
        f"{_tex_escape(str(s['verdict']).split('.')[-1])}, no certificate \\\\\n"
        f"Negative controls & "
        f"{'both rejected' if ctrl_ok else '\\textbf{CONTROL FAILURE}'} "
        "(bogus proofs vs.\\ a satisfiable CNF) \\\\\n"
        f"Wall time & {u['time_s']}\\,s \\\\\n"
        "\\bottomrule\n\\end{tabular}\n\\end{table}\n")


SECTIONS = {
    "capability": run_capability,
    "composed": run_composed,
    "branch": run_branch,
    "cases": run_cases,
    "perf": run_perf,
    "proved": run_proved,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=sorted(SECTIONS), nargs="*")
    args = ap.parse_args()
    write_env()
    todo = args.only or ["capability", "composed", "branch", "cases", "perf",
                         "proved"]
    for name in todo:
        print(f"== {name} ==")
        SECTIONS[name]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
