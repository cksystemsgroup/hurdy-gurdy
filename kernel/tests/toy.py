"""A toy registry, built from empty and admitted through the real gate.

Two languages, one pair, one search, one domain — small enough that
the whole bootstrap of KERNEL.md §8 runs in seconds, rich enough that
every channel, both grades of universal evidence, and every way of
failing the gate can be exercised.

- ``toy``: a program is ``{"threshold": T, "input_max": M}``, an input
  is ``{"x": n}``; the interpreter saturates ``x`` at ``M`` and
  reports ``bad = x > T`` and ``depth = 1``. So ``bad`` can fire iff
  ``M > T``, and the universal claim "never bad" is true iff
  ``M <= T`` — which is exactly what the certificate schema
  ``threshold-proof`` (payload ``{"input_max", "threshold"}``) lets a
  judge check from the program alone.
- ``toy2``: the same semantics under another syntax — program
  ``{"t", "m"}``, observable ``fired`` instead of ``bad`` — with the
  schema ``tm-proof`` (payload ``{"m", "t"}``).
- ``toy--toy2``: exact; ``prog`` (rename the fields), ``wit``
  (identity on inputs), ``obs`` (``maps`` bad->fired), ``claim``; its
  revision 2 adds ``cert`` (rename the payload).
- ``toy2-search``: emits the witness ``{"x": t+1}`` when ``m > t``,
  else ``all(inf)`` with a ``tm-proof`` certificate.
- ``toydom``: root ``toy`` with a stated anchor.

Every implementation here is "generated" the way everything in the
registry is — written as text, believed only after it is run — and
each carries the mutants the gate needs to falsify it.
"""

from __future__ import annotations

import hashlib
import json
import os

from kernel import driver, registry

# -- language toy -------------------------------------------------------------

TOY_INTERP = '''\
import json, sys
prog = json.load(open(sys.argv[1])); inp = json.load(open(sys.argv[2]))
x = min(int(inp.get("x", 0)), int(prog["input_max"]))
print(json.dumps({"bad": x > int(prog["threshold"]), "depth": 1},
                 sort_keys=True))
'''

TOY_MUTANT_NOBAD = '''\
import json, sys
print(json.dumps({"bad": False, "depth": 1}, sort_keys=True))
'''

TOY_MUTANT_NOSAT = '''\
import json, sys
prog = json.load(open(sys.argv[1])); inp = json.load(open(sys.argv[2]))
x = int(inp.get("x", 0))
print(json.dumps({"bad": x > int(prog["threshold"]), "depth": 1},
                 sort_keys=True))
'''

TOY_CHECK = '''\
import json, sys
prog = json.load(open(sys.argv[1])); cert = json.load(open(sys.argv[2]))
ok = (isinstance(cert, dict)
      and cert.get("input_max") == prog["input_max"]
      and cert.get("threshold") == prog["threshold"]
      and prog["input_max"] <= prog["threshold"])
obl = {"saturation": prog["input_max"], "threshold": prog["threshold"]} \\
    if ok else {}
print(json.dumps({"ok": ok, "obligations": obl}, sort_keys=True))
'''

# -- language toy2 ------------------------------------------------------------

TOY2_INTERP = '''\
import json, sys
prog = json.load(open(sys.argv[1])); inp = json.load(open(sys.argv[2]))
x = min(int(inp.get("x", 0)), int(prog["m"]))
print(json.dumps({"fired": x > int(prog["t"]), "depth": 1}, sort_keys=True))
'''

TOY2_MUTANT_NOFIRE = '''\
import json, sys
print(json.dumps({"fired": False, "depth": 1}, sort_keys=True))
'''

TOY2_CHECK = '''\
import json, sys
prog = json.load(open(sys.argv[1])); cert = json.load(open(sys.argv[2]))
ok = (isinstance(cert, dict) and cert.get("m") == prog["m"]
      and cert.get("t") == prog["t"] and prog["m"] <= prog["t"])
obl = {"m": prog["m"], "t": prog["t"]} if ok else {}
print(json.dumps({"ok": ok, "obligations": obl}, sort_keys=True))
'''

# -- pair toy--toy2 -----------------------------------------------------------

PAIR_T = '''\
import json, sys
prog = json.load(open(sys.argv[1]))
print(json.dumps({"t": prog["threshold"], "m": prog["input_max"]},
                 sort_keys=True))
'''

PAIR_T_MUTANT_SWAP = '''\
import json, sys
prog = json.load(open(sys.argv[1]))
print(json.dumps({"t": prog["input_max"], "m": prog["threshold"]},
                 sort_keys=True))
'''

PAIR_LAM_WIT = '''\
import json, sys
inp = json.load(open(sys.argv[1]))
print(json.dumps(inp, sort_keys=True))
'''

PAIR_LAM_WIT_MUTANT_DROP = '''\
import json, sys
print(json.dumps({}, sort_keys=True))
'''

PAIR_LAM_CERT = '''\
import json, sys
cert = json.load(open(sys.argv[1])); p = cert["payload"]
print(json.dumps({"schema": "threshold-proof",
                  "payload": {"input_max": p["m"], "threshold": p["t"]}},
                 sort_keys=True))
'''

PAIR_LAM_CERT_MUTANT_SWAP = '''\
import json, sys
cert = json.load(open(sys.argv[1])); p = cert["payload"]
print(json.dumps({"schema": "threshold-proof",
                  "payload": {"input_max": p["t"], "threshold": p["m"]}},
                 sort_keys=True))
'''

# -- search toy2-search -------------------------------------------------------

SEARCH_SOLVE = '''\
import json, sys
prog = json.load(open(sys.argv[1]))
if prog["m"] > prog["t"]:
    print(json.dumps({"kind": "witness", "payload": {"x": prog["t"] + 1}},
                     sort_keys=True))
else:
    print(json.dumps({"kind": "all", "bound": "inf",
                      "cert": {"schema": "tm-proof",
                               "payload": {"m": prog["m"], "t": prog["t"]}}},
                     sort_keys=True))
'''

SEARCH_MUTANT_LIAR = '''\
import json, sys
print(json.dumps({"kind": "witness", "payload": {"x": 0}}, sort_keys=True))
'''


def _j(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True) + "\n").encode()


def _prog(threshold: int, input_max: int) -> bytes:
    return _j({"threshold": threshold, "input_max": input_max})


def _prog2(t: int, m: int) -> bytes:
    return _j({"t": t, "m": m})


# -- the entries, as (manifest, files) ---------------------------------------

def domain() -> tuple[dict, dict[str, bytes]]:
    return ({"kind": "domain", "name": "toydom", "root": "toy",
             "anchors": ["three hand-written vectors with pinned "
                         "observables (registry/languages/toy/vectors)"]},
            {})


def language_toy() -> tuple[dict, dict[str, bytes]]:
    files = {
        "interp.py": TOY_INTERP.encode(),
        "vectors/001.program": _prog(5, 10),
        "vectors/001.input": _j({"x": 7}),
        "vectors/001.expect": _j({"bad": True, "depth": 1}),
        "vectors/002.program": _prog(5, 3),
        "vectors/002.input": _j({"x": 7}),
        "vectors/002.expect": _j({"bad": False, "depth": 1}),
        "vectors/003.program": _prog(5, 10),
        "vectors/003.input": _j({"x": 2}),
        "vectors/003.expect": _j({"bad": False, "depth": 1}),
        "controls/mutant_nobad.py": TOY_MUTANT_NOBAD.encode(),
        "controls/mutant_nosat.py": TOY_MUTANT_NOSAT.encode(),
        "evidence/threshold-proof/check.py": TOY_CHECK.encode(),
        "evidence/threshold-proof/vectors/001.program": _prog(5, 3),
        "evidence/threshold-proof/vectors/001.cert":
            _j({"input_max": 3, "threshold": 5}),
        "evidence/threshold-proof/vectors/002.program": _prog(9, 9),
        "evidence/threshold-proof/vectors/002.cert":
            _j({"input_max": 9, "threshold": 9}),
        "evidence/threshold-proof/controls/001.cert":
            _j({"input_max": 3, "threshold": 2}),
        "evidence/threshold-proof/controls/002.cert":
            _j({"input_max": 9, "threshold": 10}),
    }
    return ({"kind": "language", "name": "toy",
             "observables": ["bad", "depth"],
             "lineage": ["toy-interp-g1", "toy-cert-g1"]}, files)


def language_toy2() -> tuple[dict, dict[str, bytes]]:
    files = {
        "interp.py": TOY2_INTERP.encode(),
        "vectors/001.program": _prog2(5, 10),
        "vectors/001.input": _j({"x": 7}),
        "vectors/001.expect": _j({"fired": True, "depth": 1}),
        "vectors/002.program": _prog2(5, 3),
        "vectors/002.input": _j({"x": 7}),
        "vectors/002.expect": _j({"fired": False, "depth": 1}),
        "controls/mutant_nofire.py": TOY2_MUTANT_NOFIRE.encode(),
        "evidence/tm-proof/check.py": TOY2_CHECK.encode(),
        "evidence/tm-proof/vectors/001.program": _prog2(5, 3),
        "evidence/tm-proof/vectors/001.cert": _j({"m": 3, "t": 5}),
        "evidence/tm-proof/controls/001.cert": _j({"m": 3, "t": 2}),
    }
    return ({"kind": "language", "name": "toy2",
             "observables": ["fired", "depth"],
             "lineage": ["toy2-interp-g1", "toy2-cert-g1"]}, files)


def pair(revision: int = 1, previous: str | None = None
         ) -> tuple[dict, dict[str, bytes]]:
    files = {
        "T.py": PAIR_T.encode(),
        "lam_wit.py": PAIR_LAM_WIT.encode(),
        "corpus/001.program": _prog(5, 10),
        "corpus/001.input": _j({"x": 7}),
        "corpus/001.wit": _j({"x": 7}),
        "corpus/002.program": _prog(5, 3),
        "corpus/002.input": _j({"x": 1}),
        "corpus/002.wit": _j({"x": 1}),
        "controls/prog_mutant_swap.py": PAIR_T_MUTANT_SWAP.encode(),
        "controls/wit_mutant_drop.py": PAIR_LAM_WIT_MUTANT_DROP.encode(),
    }
    manifest = {"kind": "pair", "id": "toy--toy2", "src": "toy",
                "tgt": "toy2", "direction": "exact",
                "keeps": ["bad", "depth"],
                "channels": ["prog", "wit", "obs", "claim"],
                "maps": {"bad": "fired", "depth": "depth"},
                "lineage": ["toy2toy2-g1"]}
    if revision > 1:
        files["lam_cert.py"] = PAIR_LAM_CERT.encode()
        files["corpus/002.cert"] = _j({"schema": "tm-proof",
                                       "payload": {"m": 3, "t": 5}})
        files["controls/cert_mutant_swap.py"] = \
            PAIR_LAM_CERT_MUTANT_SWAP.encode()
        manifest["channels"] = manifest["channels"] + ["cert"]
        manifest["revision"] = revision
        manifest["previous"] = previous
    return manifest, files


def search() -> tuple[dict, dict[str, bytes]]:
    files = {
        "solve.py": SEARCH_SOLVE.encode(),
        "corpus/001.program": _prog2(5, 10),
        "corpus/001.q": _j({"mode": "exists", "observable": "fired",
                            "bound": "inf", "label": True}),
        "corpus/002.program": _prog2(5, 3),
        "corpus/002.q": _j({"mode": "forall", "observable": "fired",
                            "bound": "inf", "label": False}),
        "controls/mutant_liar.py": SEARCH_MUTANT_LIAR.encode(),
    }
    return ({"kind": "search", "name": "toy2-search", "language": "toy2",
             "targets": ["fired"], "lineage": ["toy2-search-g1"]}, files)


# -- building and admitting ---------------------------------------------------

def write_entry(reg_root: str, manifest: dict,
                files: dict[str, bytes]) -> str:
    """Register an entry directory (append-only) and return its path."""
    return registry.register(reg_root, manifest, files)


def admit(reg_root: str, manifest: dict, files: dict[str, bytes],
          wall_s: float = 20.0) -> tuple[str, dict]:
    """Write the entry and pass it through the one gate; returns
    (entry dir, stamped evidence). Raises AdmissionError like the
    gate does."""
    entry = write_entry(reg_root, manifest, files)
    return entry, driver.admit(entry, reg_root, wall_s=wall_s)


def build(root: str, wall_s: float = 20.0) -> str:
    """Bootstrap from empty (KERNEL.md §8): domain, the root's
    interpreter, the second language, the pair, the search — every one
    admitted through ``driver.admit``. Returns the registry root."""
    reg_root = os.path.join(root, "registry")
    os.makedirs(reg_root)
    for manifest, files in (domain(), language_toy(), language_toy2(),
                            pair(), search()):
        admit(reg_root, manifest, files, wall_s)
    return reg_root


def admit_cert_revision(reg_root: str, wall_s: float = 20.0) -> str:
    """The canonical (b)-move of KERNEL.md §8: the pair learns to carry
    certificates home, by revision."""
    prev = registry.tree_hash(os.path.join(reg_root, "pairs", "toy--toy2"))
    manifest, files = pair(revision=2, previous=prev)
    entry, _ = admit(reg_root, manifest, files, wall_s)
    return entry


def write_benchmark(run_dir: str) -> dict:
    """A two-question benchmark at ``toy``: one unsafe program asked
    ``exists bad``, one safe program asked ``forall bad`` at ``inf``."""
    os.makedirs(run_dir, exist_ok=True)
    programs = {"unsafe.json": _prog(5, 10), "safe.json": _prog(5, 3)}
    questions = []
    for qid, fn, mode in (("q-unsafe", "unsafe.json", "exists"),
                          ("q-safe", "safe.json", "forall")):
        data = programs[fn]
        with open(os.path.join(run_dir, fn), "wb") as fh:
            fh.write(data)
        questions.append({"id": qid, "language": "toy", "program": fn,
                          "sha256": hashlib.sha256(data).hexdigest(),
                          "mode": mode, "observable": "bad",
                          "bound": "inf"})
    bench = {"name": "toy-bench", "domain": "toydom",
             "questions": questions}
    with open(os.path.join(run_dir, "benchmark.json"), "w",
              encoding="utf-8") as fh:
        json.dump(bench, fh, indent=1, sort_keys=True)
    return bench


def question(run_dir: str, qid: str) -> dict:
    """A question dict as the driver sees it (program path resolved)."""
    from kernel import results
    bench = results.load_benchmark(os.path.join(run_dir, "benchmark.json"))
    return next(q for q in bench["questions"] if q["id"] == qid)


def unstamped_search(root: str, name: str, solve_src: str,
                     lineage: list[str]) -> dict:
    """A search manifest the driver can run directly — for the routes
    ``test_forge`` builds by hand, where what matters is what the
    kernel does with a search's output, not whether the search would
    pass the gate."""
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "solve.py"), "w", encoding="utf-8") as fh:
        fh.write(solve_src)
    return {"kind": "search", "name": name, "language": "toy2",
            "targets": ["fired"], "lineage": lineage, "_dir": d,
            "admission": {"checked": "search"}}
