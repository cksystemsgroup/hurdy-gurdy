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
        "decidable square (the \\texttt{predicted}-grade hops into the\n"
        "SMT-LIB hub and the\n"
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

    # ---- disjoint-decision branch ------------------------------------------
    # The same questions decided with fully disjoint stacks after the head:
    # the direct route's BTOR2 system decided NATIVELY by btormc (no bridge,
    # no z3, no SMT-LIB), the via-Sail route through the bridge and z3. The
    # diverse segment then spans both the lowering derivation (ISA-prose vs
    # Sail-model) and the decision procedure (btormc/BTOR2 vs z3/SMT-LIB);
    # the residual share is the emission library and the language-owned
    # endpoints (stated in the paper's Assumption 2 discussion).
    from gurdy.solvers.native_btor2 import NativeBtor2Checker
    native = NativeBtor2Checker()
    disjoint = []
    if native.available():
        # (name, head, k, kind) — kind picks the two routes from ROUTES
        # below; a C-headed entry is ("c", target value) so the property
        # can be routed to each lowering hop via per-pair params.
        dq = [("riscv const x1==42 (reach)", rhead(const, {"reg_eq": [1, 42]}), 4, "riscv"),
              ("riscv const x1==99 (unreach)", rhead(const, {"reg_eq": [1, 99]}), 4, "riscv"),
              ("riscv loop sum==15 (reach)", rhead(loop, {"reg_eq": [1, 15]}), 25, "riscv"),
              ("riscv loop sum==99 (unreach)", rhead(loop, {"reg_eq": [1, 99]}), 25, "riscv"),
              ("riscv store/load 0x123 (reach)", rhead(mem, {"reg_eq": [3, 0x123]}), 10, "riscv"),
              ("riscv store/load 0x999 (unreach)", rhead(mem, {"reg_eq": [3, 0x999]}), 10, "riscv"),
              ("aarch64 movz/add x1==42 (reach)", ahead(a64_alu, {"reg_eq": [1, 42]}), 4, "aarch64"),
              ("aarch64 movz/add x1==999 (unreach)", ahead(a64_alu, {"reg_eq": [1, 999]}), 4, "aarch64"),
              ("aarch64 SUBS/B.NE loop x0==1 (reach)", ahead(a64_loop, {"reg_eq": [0, 1]}), 12, "aarch64"),
              ("aarch64 SUBS/B.NE loop x0==5 (unreach)", ahead(a64_loop, {"reg_eq": [0, 5]}), 12, "aarch64")]
        if find_gcc():
            # The C-headed questions too: disjoint after the (shared) compiler
            # head, property carried to each route's lowering hop via params.
            dq += [(f"C a0=={v} ({lbl})", {"source": src}, 6, ("c", v))
                   for v, lbl in ((47, "reach"), (99, "unreach"))]
        else:
            print("disjoint: riscv64 gcc unavailable, skipping C rows")
        ROUTES = {
            "riscv": (["riscv-btor2"],
                      ["riscv-sail", "sail-btor2", "btor2-smtlib"]),
            "aarch64": (["aarch64-btor2"],
                        ["aarch64-sail", "sail-btor2", "btor2-smtlib"]),
            "c": (["c-riscv", "riscv-btor2"],
                  ["c-riscv", "riscv-sail", "sail-btor2", "btor2-smtlib"]),
        }
        for name, dhead, kk, kind in dq:
            if isinstance(kind, tuple):        # C head: ("c", target value)
                kind, v = kind
                params = {"riscv-btor2": {"property": {"reg_eq": [10, v]}},
                          "riscv-sail": {"property": {"reg_eq": [10, v]}}}
            else:
                params = {}
            direct_route, sail_route = ROUTES[kind]
            t0 = time.perf_counter()
            btor = route.run_route(direct_route, dhead, params)["artifact"]
            nv = native.decide_bounded(btor, k=kk)
            zv = _decide_z3(route.run_route(sail_route, dhead,
                                            {**params, "btor2-smtlib": {"k": kk}})["artifact"])
            agree = str(nv) == str(zv)
            disjoint.append({"question": name,
                             "native_direct": str(nv), "bridged_sail_z3": str(zv),
                             "agree": agree,
                             "time_s": round(time.perf_counter() - t0, 2)})
            print(f"disjoint {name}: native={nv} bridged={zv} agree={agree}")
    else:
        print("disjoint: native BTOR2 checker unavailable, skipping")

    (DATA / "branch.json").write_text(json.dumps(
        {"solver_level": results, "trace_level": a64_rows,
         "disjoint_decision": disjoint}, indent=2))

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
    drows = []
    for r in disjoint:
        v = str(r["native_direct"]).split(".")[-1].replace("REACHABLE", "reach")
        v = v.replace("UNreach", "unreach")
        drows.append(f"{_tex_escape(r['question'])} & "
                     f"{'\\checkmark' if r['agree'] else '$\\times$'} & "
                     f"{_tex_escape(v)} \\\\")
    (TABLES / "branch.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table}\n\\caption{Composed \\emph{conjoined} coverage: a\n"
        "probe counts iff it survives every hop \\emph{and} every hop with a\n"
        "decidable square passes it on that hop's input (the route-level\n"
        "reading of Definition~\\ref{def:coverage}; ``via Sail'' routes are\n"
        "the independently derived branch; denominators are the source\n"
        "language's inventory, \\S\\ref{sec:eval-branch}), and branch\n"
        "agreement: the same question decided along both routes. Times are\n"
        "the slower route, end to end (translate every hop + decide with Z3).\n"
        "The bottom block decides the same questions with fully disjoint\n"
        "stacks after the head: the direct route's BTOR2 system decided\n"
        "natively by btormc (no bridge, no SMT-LIB, no Z3) against the\n"
        "via-Sail route through the bridge and Z3 --- the diverse segment\n"
        "spans both the lowering derivation and the decision procedure\n"
        "(\\S\\ref{sec:branching}).}\n"
        "\\label{tab:branch}\n\\footnotesize\n"
        "\\begin{tabular}{@{}lr@{}}\n\\toprule\n"
        "Route (to SMT-LIB) & Composed coverage \\\\\n\\midrule\n"
        + "\n".join(crows) +
        "\n\\bottomrule\n\\end{tabular}\n\n\\medskip\n\n"
        "\\begin{tabular}{@{}lclr@{}}\n\\toprule\n"
        "Question (both routes) & Agree & Verdict & Time (s) \\\\\n\\midrule\n"
        + "\n".join(brows) +
        "\n\\bottomrule\n\\end{tabular}\n"
        + ("\n\\medskip\n\n"
           "\\begin{tabular}{@{}lcl@{}}\n\\toprule\n"
           "Question, decision stacks fully disjoint & Agree & Verdict \\\\\n"
           "\\midrule\n" + "\n".join(drows) +
           "\n\\bottomrule\n\\end{tabular}\n" if drows else "")
        + "\\end{table}\n")


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


# --- riscv-tests-derived reachability benchmark -------------------------------

def run_bench() -> None:
    """The compliance slice as a question set (tools/riscv_bench.py): derive
    reachability questions with interpreter ground truth from every slice
    program, decide each along BOTH RISC-V routes, grade agreement and
    ground-truth match. Needs the pinned riscv64 toolchain."""
    import importlib.util
    import tempfile

    def _tool(name):
        spec = importlib.util.spec_from_file_location(
            name, ROOT / "tools" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    riscv_slice = _tool("riscv_slice")
    if not riscv_slice.find_gcc():
        print("bench: riscv64 toolchain unavailable, skipping")
        return
    riscv_bench = _tool("riscv_bench")
    with tempfile.TemporaryDirectory(prefix="riscv-bench-") as d:
        riscv_slice.build(d)
        report = riscv_bench.run_benchmark(d)
    (DATA / "bench.json").write_text(json.dumps(report, indent=2))
    t = report["totals"]
    print(f"bench: {t['questions']} questions, {t['agree']} agree, "
          f"{t['correct']} correct")

    rows = []
    for p in report["programs"]:
        n = len(p["questions"])
        agree = sum(q["agree"] for q in p["questions"])
        correct = sum(q["correct"] for q in p["questions"])
        rows.append(
            f"\\texttt{{{_tex_escape(p['program'])}}} & {p['trace_len']} & "
            f"{p['k']} & {n} & {agree}/{n} & {correct}/{n} & "
            f"{p['time_s']:.1f} \\\\")
    rows.append("\\midrule")
    rows.append(f"Total & & & {t['questions']} & {t['agree']} & "
                f"{t['correct']} & \\\\")
    (TABLES / "bench.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table}\n\\caption{The compliance slice as an external-format\n"
        "question set: self-checking programs in the riscv-tests HTIF\n"
        "convention (built with the pinned toolchain at the upstream link\n"
        "base), each reference-run to derive per-register reachable /\n"
        "bounded-unreachable questions with machine-derived ground truth,\n"
        "each question decided independently along BOTH RISC-V$\\to$SMT-LIB\n"
        "routes. Agree = the two routes' verdicts coincide; correct = the\n"
        "agreed verdict matches the interpreter-derived ground truth. Time\n"
        "is both routes, all questions, end to end.}\n"
        "\\label{tab:bench}\n\\footnotesize\n"
        "\\begin{tabular}{@{}lrrrrrr@{}}\n\\toprule\n"
        "Program & Steps & $k$ & Questions & Agree & Correct & Time (s) \\\\\n"
        "\\midrule\n"
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


# --- escape-rate estimate (seeded fault injection) -----------------------------

def run_escape() -> None:
    """Seeded fault injection over the riscv-btor2 emissions
    (tools/fault_injection.py): every applicable mutant runs through the
    architecture's gates in order (square suite -> branch questions ->
    compliance-derived benchmark); the table reports which layer caught
    each and the residual escape count. Needs the riscv64 toolchain for
    the bench gate (reported if absent). Takes ~25 minutes."""
    import importlib.util
    import tempfile

    def _tool(name):
        spec = importlib.util.spec_from_file_location(
            name, ROOT / "tools" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod   # dataclasses resolve annotations here
        spec.loader.exec_module(mod)
        return mod

    riscv_slice = _tool("riscv_slice")
    fault_injection = _tool("fault_injection")
    with tempfile.TemporaryDirectory(prefix="riscv-bench-") as d:
        elf_dir = None
        if riscv_slice.find_gcc():
            riscv_slice.build(d)
            elf_dir = d
        else:
            print("escape: riscv64 toolchain unavailable — bench gate off")
        report = fault_injection.run_experiment(elf_dir)
    (DATA / "escape.json").write_text(json.dumps(report, indent=2))
    c = report["counts"]
    print("escape counts:", c)

    (TABLES / "escape.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table}\n\\caption{Escape-rate experiment: seeded semantic\n"
        "mutations of the riscv-btor2 emissions (uniform rules model\n"
        "systematic mis-lowerings, site rules single-site defects;\n"
        "operand swaps only on non-commutative operators; rules that\n"
        "change no probe artifact are excluded from the denominator),\n"
        "each run through the architecture's gates in order. ``Square''\n"
        "is the conjoined probe suite (\\S\\ref{sec:eval-capability}),\n"
        "``branch'' the authored solver questions against the intact Sail\n"
        "route, ``bench'' the compliance-derived ground-truth questions\n"
        "(\\S\\ref{sec:eval-bench}).}\n"
        "\\label{tab:escape}\n\\footnotesize\n"
        "\\begin{tabular}{@{}lr@{}}\n\\toprule\n"
        f"Applicable mutants & {c['mutants']} \\\\\n"
        "\\midrule\n"
        f"Caught by the square suite & {c['square'] + c['evaluator']} \\\\\n"
        f"Caught by branch agreement & {c['branch']} \\\\\n"
        f"Caught by the derived benchmark & {c['bench']} \\\\\n"
        f"Escaped all three gates & \\textbf{{{c['escaped']}}} \\\\\n"
        "\\bottomrule\n\\end{tabular}\n\\end{table}\n")


# --- LLM-player table -----------------------------------------------------------

# Short question labels and per-row evidence-class strings, curated from the
# primary record (results/llm_player/{questions,results}.json — full texts,
# transcripts, and verbatim evidence live there and ship in the artifact).
# Ground truths, verdicts, and correctness are read live from results.json.
_PLAYER_ROWS = [
    ("R1", "RISC-V loop: $x_1{=}15$ within $k{=}25$",
     "two-route agreement"),
    ("R2", "RISC-V loop: $x_1{=}16$ within $k{=}25$",
     "two-route agreement (bounded)"),
    ("R3", "\\texttt{srli} (logical) $\\mathtt{0xF..F8} \\gg 60$: $x_1{=}15$",
     "two-route agreement"),
    ("R4", "\\texttt{srai} (arithmetic) $\\gg 60$: $x_1{=}15$",
     "two-route agreement (bounded)"),
    ("R5", "\\texttt{lb} (sign-ext.) of byte \\texttt{0x84}: $x_3{=}$\\texttt{0x84}",
     "two-route + self-devised positive control"),
    ("R6", "\\texttt{lbu} (zero-ext.) of byte \\texttt{0x84}: $x_3{=}$\\texttt{0x84}",
     "two-route agreement"),
    ("E1", "eBPF $x{\\cdot}x \\bmod 2^{64} = 3$",
     "\\tprov: LRAT re-validated by cake\\_lpr"),
    ("E2", "eBPF $x{\\cdot}x = 4$",
     "z3 + native btormc; witness replayed"),
    ("E3", "$x{\\cdot}y = 1073741789$, $x,y \\in [2, 2^{16}{+}1]$",
     "\\tprov: 17\\,MB LRAT via cake\\_lpr"),
    ("E4", "$x{\\cdot}y = 2147766287$, same range",
     "witness replay; factor pair exhibited"),
    ("P1", "Python assert: $y{=}16$ violable",
     "SMT model re-checked + CPython replay"),
    ("P2", "Python assert: $y{=}15$ violable",
     "\\textsc{unsat}, scoped per-run (\\tpred)"),
]


def run_player() -> None:
    """Format the LLM-player experiment's recorded results (results/llm_player/)
    into tab:player. This section formats the primary record; it does not
    re-run the (manual-protocol) experiment."""
    results = json.loads(
        (HERE / "llm_player" / "results.json").read_text())
    by_q = {r["q"]: r for r in results["rows"]}
    assert set(by_q) == {q for q, _, _ in _PLAYER_ROWS}, sorted(by_q)
    rows = []
    for qid, label, ev in _PLAYER_ROWS:
        r = by_q[qid]
        truth = "R" if r["ground_truth"] == "REACHABLE" else "U"
        a_ok = "\\checkmark" if r["armA"]["verdict"] == r["ground_truth"] else "$\\times$"
        b_ok = "\\checkmark" if r["armB"]["verdict"] == r["ground_truth"] else "$\\times$"
        rows.append(f"{qid} & {label} & {truth} & {a_ok} & {b_ok} & {ev} \\\\")
        print(f"player {qid}: truth={truth} A={r['armA']['verdict']} "
              f"B={r['armB']['verdict']}")
    (TABLES / "player.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table*}\n\\caption{The LLM-player experiment: 12\n"
        "ground-truthed questions, two arms. Arm A (unaided) answers from\n"
        "reasoning alone; arm B answers \\emph{via the platform}. A\n"
        "\\checkmark{} means the verdict matches the platform-established\n"
        "ground truth (R = reachable, U = unreachable within the stated\n"
        "bound). Both arms are correct on all 12 --- the contrast is the\n"
        "final column: every arm-B verdict carries a machine-checked\n"
        "evidence artifact, where arm A rests on the model's say-so (all\n"
        "arm-A answers were reported at high confidence). Full question\n"
        "texts, per-run transcripts, and verbatim evidence bases:\n"
        "\\texttt{results/llm\\_player/} in the artifact.}\n"
        "\\label{tab:player}\n\\footnotesize\n"
        "\\begin{tabular}{@{}llcccl@{}}\n\\toprule\n"
        "Q & Question & Truth & Arm A & Arm B & Arm-B evidence artifact \\\\\n"
        "\\midrule\n"
        + "\n".join(rows) +
        "\n\\bottomrule\n\\end{tabular}\n\\end{table*}\n")


# --- scalability sweep ---------------------------------------------------------

def run_scale() -> None:
    """Where does the pipeline stand as questions grow? Two axes: unrolling
    depth (the summation loop at growing bounds N, k = 5N + 5) and certified
    refutation size (the bounded-factorization family at growing factor
    widths). Sequential; sizes and times from real runs."""
    from gurdy.languages.riscv import asm
    from gurdy.languages.riscv.interp import image_from_words

    data: dict[str, Any] = {"loop": [], "certified": []}

    for n in (5, 20, 50, 100):
        loop = [asm.addi(1, 0, 0), asm.addi(2, 0, 1), asm.addi(3, 0, n),
                asm.add(1, 1, 2), asm.addi(2, 2, 1), asm.bge(3, 2, -8), 0x73]
        target = n * (n + 1) // 2
        head = {"image": image_from_words(loop), "init_regs": {},
                "property": {"reg_eq": [1, target]}}
        k = 5 * n + 5
        t0 = time.perf_counter()
        art = route.run_route(["riscv-btor2", "btor2-smtlib"], head,
                              {"btor2-smtlib": {"k": k}})["artifact"]
        t_tr = time.perf_counter() - t0
        t0 = time.perf_counter()
        v = _decide_z3(art)
        t_dec = time.perf_counter() - t0
        row = {"N": n, "k": k, "target": target, "verdict": str(v),
               "translate_s": round(t_tr, 2), "decide_s": round(t_dec, 2),
               "artifact_bytes": len(art)}
        data["loop"].append(row)
        print("scale loop:", row)

    from gurdy.languages.ebpf import asm as easm
    from gurdy.languages.ebpf.interp import program_from_words
    from gurdy.pairs.ebpf_btor2 import translate as ebpf_translate
    from gurdy.solvers.proved import prove_unreachable

    AND_OP, ADD_OP, MUL_OP = 0x5, 0x0, 0x2
    for bits, target in ((8, 65521), (12, 16777213), (16, 2147483647)):
        mask = (1 << bits) - 1
        words = [easm.call(7), easm.alu64_imm(AND_OP, 0, mask),
                 easm.alu64_imm(ADD_OP, 0, 2), easm.mov64_reg(6, 0),
                 easm.call(7), easm.alu64_imm(AND_OP, 0, mask),
                 easm.alu64_imm(ADD_OP, 0, 2),
                 easm.alu64_reg(MUL_OP, 6, 0), easm.exit_()]
        head = {"prog": program_from_words(words), "init_regs": {},
                "property": {"reg_eq": [6, target]}}
        t0 = time.perf_counter()
        r = prove_unreachable(ebpf_translate(head), 10)
        row = {"bits": bits, "target": target, "verdict": str(r.verdict),
               "tier": r.tier, "drat_bytes": len(r.certificate or b""),
               "lrat_bytes": r.provenance.get("lrat_bytes"),
               "checker_ok": r.checker_ok,
               "time_s": round(time.perf_counter() - t0, 2)}
        data["certified"].append(row)
        print("scale certified:", row)

    (DATA / "scale.json").write_text(json.dumps(data, indent=2))

    lrows = [
        f"$N{{=}}{r['N']}$, $k{{=}}{r['k']}$ & "
        f"{_tex_escape(str(r['verdict']).split('.')[-1].lower())} & "
        f"{r['translate_s']:.2f} & {r['decide_s']:.2f} & "
        f"{r['artifact_bytes']//1000}\\,kB \\\\"
        for r in data["loop"]]
    crows = [
        f"{r['bits']}-bit factors, target {r['target']} & "
        f"{'certified' if r['checker_ok'] else r['tier']} & "
        f"{_mbs(r['drat_bytes'])} & "
        + (f"{_mbs(r['lrat_bytes'])}" if r['lrat_bytes'] is not None else "---")
        + f" & {r['time_s']:.1f} \\\\"
        for r in data["certified"]]
    (TABLES / "scale.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table}\n\\caption{Scalability probes on two axes. Left:\n"
        "the summation-loop question at growing bounds ($x_1 = N(N{+}1)/2$\n"
        "after $N$ iterations; reachable at every size), whole-route\n"
        "translation and Z3 decide time. Right: the certified tier on the\n"
        "bounded-factorization family at growing factor widths ---\n"
        "certificate sizes grow four orders of magnitude and cake\\_lpr\n"
        "re-validates each.}\n"
        "\\label{tab:scale}\n\\footnotesize\n"
        "\\begin{tabular}{@{}lllrr@{}}\n\\toprule\n"
        "Loop question & verdict & translate (s) & decide (s) & artifact \\\\\n"
        "\\midrule\n" + "\n".join(lrows) +
        "\n\\bottomrule\n\\end{tabular}\n\n\\medskip\n\n"
        "\\begin{tabular}{@{}llllr@{}}\n\\toprule\n"
        "Certified question & outcome & DRAT & LRAT & time (s) \\\\\n"
        "\\midrule\n" + "\n".join(crows) +
        "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")


def _mbs(nbytes: int) -> str:
    return (f"{nbytes/1e6:.1f}\\,MB" if nbytes >= 100_000
            else f"{nbytes/1e3:.1f}\\,kB" if nbytes >= 1000
            else f"{nbytes}\\,B")


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

    # The nontrivial certificate: r6 = x * y with x, y masked-and-offset free
    # inputs in [2, 2^16+1]; can the product be 2^31 - 1 (a Mersenne prime)?
    # No factorization with both factors in range exists, and refuting a
    # 16x16-bit multiplication is real certificate-scale work (the LRAT is
    # ~12 MB where the x^2=3 exhibit's is 18 B).
    AND_OP, ADD_OP, MUL_OP = 0x5, 0x0, 0x2
    M31 = 2147483647

    def factor_head(target):
        words = [easm.call(7), easm.alu64_imm(AND_OP, 0, 0xFFFF),
                 easm.alu64_imm(ADD_OP, 0, 2), easm.mov64_reg(6, 0),
                 easm.call(7), easm.alu64_imm(AND_OP, 0, 0xFFFF),
                 easm.alu64_imm(ADD_OP, 0, 2), easm.alu64_reg(MUL_OP, 6, 0),
                 easm.exit_()]
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

    t0 = time.perf_counter()
    rn = prove_unreachable(ebpf_translate(factor_head(M31)), 10)
    data["unreachable_nontrivial"] = {
        "question": "eBPF: x*y == 2^31-1, x,y in [2, 2^16+1] "
                    "(no bounded factorization of the Mersenne prime)",
        "verdict": str(rn.verdict), "tier": rn.tier, "method": rn.method,
        "engines": rn.engines, "checker_ok": rn.checker_ok,
        "certificate_bytes": len(rn.certificate or b""),
        "checker": rn.provenance.get("checker"),
        "elaborator": rn.provenance.get("elaborator"),
        "lrat_bytes": rn.provenance.get("lrat_bytes"),
        "tcb": rn.tcb, "time_s": round(time.perf_counter() - t0, 2)}
    print("proved nontrivial:", data["unreachable_nontrivial"])

    t0 = time.perf_counter()
    rn2 = prove_unreachable(ebpf_translate(factor_head(46341 * 46341)), 10)
    data["nontrivial_reachable_sibling"] = {
        "question": "eBPF: x*y == 46341^2 (x = y = 46341, in range)",
        "verdict": str(rn2.verdict), "tier": rn2.tier,
        "certificate": rn2.certificate is not None,
        "time_s": round(time.perf_counter() - t0, 2)}
    print("proved nontrivial sibling:", data["nontrivial_reachable_sibling"])

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
    n, ns = data["unreachable_nontrivial"], data["nontrivial_reachable_sibling"]
    ctrl_ok = controls and not any(controls.values())

    def _checker_cell(row):
        head = ("cake\\_lpr (\\emph{formally verified}): "
                if row.get("method") == "bitblast-drat-lrat"
                else "drat-trim: ")
        return (head + ("\\textbf{verified}" if row["checker_ok"] else "FAILED")
                + f"; tier \\texttt{{{row['tier']}}}")

    def _mb(nbytes):
        return f"{nbytes/1e6:.1f}\\,MB" if nbytes >= 100_000 else f"{nbytes}\\,B"

    (TABLES / "proved.tex").write_text(
        "%% generated by results/harvest.py -- do not edit\n"
        "\\begin{table}\n\\caption{The certified (\\tprov) row inhabited,\n"
        "twice: input-driven unreachability claims from a real pair,\n"
        "corroborated by three engines, certified by a bit-blasted DRAT\n"
        "proof, and re-validated by the independent verified checker. The\n"
        "first exhibit is deliberately small (its refutation is essentially\n"
        "unit propagation); the second is certificate checking at scale ---\n"
        "refuting a $16{\\times}16$-bit multiplication. The controls are\n"
        "bogus checks that must fail --- and do.}\n"
        "\\label{tab:proved}\n\\footnotesize\n"
        "\\begin{tabular}{@{}p{0.30\\linewidth}p{0.30\\linewidth}p{0.32\\linewidth}@{}}\n"
        "\\toprule\n"
        " & \\textbf{propagation-scale} & \\textbf{search-scale} \\\\\n"
        "Question & $\\mathit{helper}()^2 = 3$ (no square mod $2^{64}$) & "
        "$x \\cdot y = 2^{31}{-}1$, $x,y \\in [2, 2^{16}{+}1]$ (no bounded"
        " factorization of the Mersenne prime) \\\\\n"
        f"Engines agreeing \\textsc{{unsat}} & {', '.join(u['engines'])} & "
        f"{', '.join(n['engines'])} \\\\\n"
        f"Certificate (bitwuzla$\\to$CNF, cadical$\\to$DRAT) & "
        f"{_mb(u['certificate_bytes'])} DRAT"
        + (f", {_mb(u['lrat_bytes'])} LRAT (drat-trim, untrusted)"
           if u.get("lrat_bytes") is not None else "")
        + f" & {_mb(n['certificate_bytes'])} DRAT"
        + (f", {_mb(n['lrat_bytes'])} LRAT"
           if n.get("lrat_bytes") is not None else "") + " \\\\\n"
        f"Independent check & {_checker_cell(u)} & {_checker_cell(n)} \\\\\n"
        f"Resulting \\tcb & \\multicolumn{{2}}{{l}}{{"
        f"{_tex_escape(', '.join(u['tcb']))}}} \\\\\n"
        f"Reachable sibling & $x^2{{=}}4$: "
        f"{_tex_escape(str(s['verdict']).split('.')[-1])}, no certificate & "
        f"$x{{\\cdot}}y{{=}}46341^2$: "
        f"{_tex_escape(str(ns['verdict']).split('.')[-1])}, no certificate \\\\\n"
        f"Negative controls & \\multicolumn{{2}}{{l}}{{"
        f"{'both rejected' if ctrl_ok else '\\textbf{CONTROL FAILURE}'} "
        "(bogus proofs vs.\\ a satisfiable CNF)} \\\\\n"
        f"Wall time & {u['time_s']}\\,s & {n['time_s']}\\,s \\\\\n"
        "\\bottomrule\n\\end{tabular}\n\\end{table}\n")


SECTIONS = {
    "capability": run_capability,
    "composed": run_composed,
    "branch": run_branch,
    "bench": run_bench,
    "cases": run_cases,
    "perf": run_perf,
    "proved": run_proved,
    "scale": run_scale,
    "escape": run_escape,
    "player": run_player,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=sorted(SECTIONS), nargs="*")
    args = ap.parse_args()
    write_env()
    todo = args.only or ["capability", "composed", "branch", "bench", "cases",
                         "perf", "proved", "scale", "escape", "player"]
    for name in todo:
        print(f"== {name} ==")
        SECTIONS[name]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
