"""Admission — the one gate (KERNEL.md §§1–3, §8).

One discipline for every entry: determinism is measured (run twice,
byte-compare), the checkable relation is run on the entry's own corpus,
and controls are two-sided — the intact implementation must pass and
every supplied mutant must fail. A checker that cannot be made to fail
is unfalsifiable, not checked; admission therefore *requires* at least
one vector/corpus item and at least one mutant.

The generation rule (KERNEL.md §2) is enforced here and in the sealed
runner: every reference implementation the gate runs must be generated
Python living inside the entry — there are no existing tools to wrap,
and the sandbox has no environment to find one in. An entry may ship
one **accelerator** — the same implementation in a performance-oriented
language — and only for translation or solving, whose outputs are
checked downstream; it is admitted solely by byte-agreement with the
Python reference on every admission invocation, and the reference
remains the semantics. Interpretation, carry-back, and discharge are
never accelerated: the check itself stays reference Python.

Conventions inside an entry directory:

- language:  ``interp.py <program> <input>`` -> observables JSON;
  ``vectors/NNN.{program,input,expect}``; ``controls/mutant_*.py``.
- pair (translation): ``T.py <program>`` -> target program;
  ``lam.py <input> <program>`` -> source input (carries behaviors back;
  optional, but witnesses cannot cross a hop without it);
  ``lam_obs.py <target-obs-json>`` -> source observables (optional: the
  square's Λ on observables, for pairs whose languages name their
  observables differently — absent, Λ is the identity and both sides
  must emit the same keys); ``corpus/NNN.program`` (+ ``NNN.input``);
  ``controls/mutant_*.py``.
- terminal: ``solve.py <program> <mode> <observable> <bound> <wall_s>``
  -> result-value JSON; ``lam.py <witness-payload> <program>`` ->
  interpreter input; ``corpus/NNN.{program,q}`` with labels;
  ``controls/mutant_*.py``. Optionally
  ``discharge.py <program> <cert-file>`` ->
  ``{"ok": bool, "obligations": {...}}``: the certifier the kernel runs
  on every ``all`` value carrying a ``cert`` (KERNEL.md §3 — certified
  at the source, checked past translation hops, claimed on any
  failure). A terminal that ships one must exercise it during admission
  (some corpus certificate must discharge) and must supply
  ``controls/cert_mutant_*.json`` certificates that fail to.
- domain: manifest only — the root language's name and the non-empty
  anchors (labels, supplied vectors, provenance): the ungenerable half.
"""

from __future__ import annotations

import glob
import json
import os
import tempfile

from . import registry, results, runner

_DEFAULT_WALL_S = 60.0

#: The only executables an accelerator may replace: the checked steps.
_ACCELERABLE = ("T.py", "solve.py")


class AdmissionError(Exception):
    """The entry failed admission; the message says exactly where."""


def _items(entry_dir: str, sub: str, ext: str) -> list[str]:
    return sorted(glob.glob(os.path.join(entry_dir, sub, f"*.{ext}")))


def _mutants(entry_dir: str) -> list[str]:
    return sorted(glob.glob(os.path.join(entry_dir, "controls",
                                         "mutant_*.py")))


def _json_out(res: runner.RunResult, what: str) -> dict:
    if not res.ok:
        raise AdmissionError(f"{what}: rc={res.rc} timed_out={res.timed_out} "
                             f"err={res.err[:200]!r}")
    try:
        return json.loads(res.out)
    except json.JSONDecodeError as exc:
        raise AdmissionError(f"{what}: not JSON ({exc}): {res.out[:200]!r}")


def _tmp(data: bytes, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return path


# -- the generation rule ------------------------------------------------------

def _reference(entry_dir: str, name: str) -> str:
    """The generation rule's static half: the reference implementation
    is generated Python living inside the entry. (The dynamic half is
    the sealed runner: no environment, no PATH, no existing tool.)"""
    path = os.path.join(entry_dir, name)
    if not os.path.isfile(path):
        raise AdmissionError(f"{entry_dir}: missing {name} — every "
                             "implementation is generated, inside the entry")
    if not name.endswith(".py"):
        raise AdmissionError(f"{name}: reference implementations are Python")
    return path


def _check_accelerator(entry_dir: str, manifest: dict,
                       invocations: list[list[str]],
                       wall_s: float) -> dict | None:
    """The performance seam (KERNEL.md §2): one accelerator per entry,
    translation or solving only, admitted by byte-agreement with the
    Python reference on every admission invocation. The reference
    remains the semantics; the accelerator is only ever a cheaper way
    to the same bytes — and whatever it emits at play time is still
    checked downstream (witnesses replay, universals grade)."""
    acc = manifest.get("accelerator")
    if acc is None:
        return None
    for field in ("replaces", "exe", "source", "language"):
        if field not in acc:
            raise AdmissionError(f"accelerator missing {field!r}")
    if acc["replaces"] not in _ACCELERABLE:
        raise AdmissionError(
            f"accelerator may replace only {_ACCELERABLE} — checking "
            "(interpretation, carry-back, discharge) stays reference Python")
    exe = os.path.join(entry_dir, acc["exe"])
    if not os.path.isfile(exe):
        raise AdmissionError(f"accelerator exe missing: {acc['exe']}")
    if not os.path.isfile(os.path.join(entry_dir, acc["source"])):
        raise AdmissionError(f"accelerator source missing: {acc['source']} — "
                             "the generated text is part of the entry")
    reference = _reference(entry_dir, acc["replaces"])
    if not invocations:
        raise AdmissionError("accelerator never exercised — empty corpus")
    for args in invocations:
        ref, same = runner.run_twice(reference, args, wall_s=wall_s)
        if not same or not ref.ok:
            raise AdmissionError(f"{reference}: failed or nondeterministic "
                                 "replaying the accelerator invocations")
        fast, same = runner.run_twice(exe, args, wall_s=wall_s)
        if not same:
            raise AdmissionError(f"{exe}: nondeterministic or timed out")
        if not fast.ok:
            raise AdmissionError(f"{exe}: rc={fast.rc} "
                                 f"err={fast.err[:200]!r}")
        if fast.out != ref.out:
            raise AdmissionError(f"accelerator disagrees with the reference "
                                 f"on {' '.join(args)!r}")
    return {"replaces": acc["replaces"], "language": acc["language"],
            "agreed": len(invocations)}


def _no_accelerator(entry_dir: str, manifest: dict) -> None:
    if manifest.get("accelerator") is not None:
        raise AdmissionError(f"{entry_dir}: this kind cannot be "
                             f"accelerated — only {_ACCELERABLE}")


# -- revision, not mutation ---------------------------------------------------

def _agree_run(script: str, args: list[str], wall_s: float) -> bytes:
    res, same = runner.run_twice(script, args, wall_s=wall_s)
    if not same or not res.ok:
        raise AdmissionError(f"{script}: failed or nondeterministic while "
                             "replaying the revision agreement")
    return res.out


def _check_revision(reg: dict, entry_dir: str, manifest: dict,
                    wall_s: float) -> dict | None:
    """The conservativity gate (KERNEL.md §8): a revision is admitted
    against its predecessor. The predecessor must exist, be admitted,
    and still match its content pin; the manifest's ``previous`` must
    name that exact content; and the new implementation must
    byte-agree with the old on the old entry's checkable surface —
    its vectors or corpus, plus (for a language) the corpora of every
    admitted pair bound to it. Agreement is what lets dependent stamps
    keep their meaning; the new fragment is then checked by the
    ordinary kind gate like any first admission."""
    rev = manifest.get("revision", 1)
    if rev == 1:
        return None
    if not isinstance(rev, int) or rev < 2:
        raise AdmissionError(f"revision must be an integer >= 2, got {rev!r}")
    key = manifest.get("name") or manifest.get("id")
    kind_dir = os.path.dirname(entry_dir)
    prev_dir = os.path.join(kind_dir,
                            key if rev == 2 else f"{key}@{rev - 1}")
    if not os.path.isdir(prev_dir):
        raise AdmissionError(f"predecessor missing: {prev_dir}")
    with open(os.path.join(prev_dir, "manifest.json"),
              encoding="utf-8") as fh:
        prev = json.load(fh)
    if "admission" not in prev:
        raise AdmissionError(f"{prev_dir}: predecessor was never admitted")
    root = registry.tree_hash(prev_dir)
    stamped = prev["admission"].get("tree")
    if stamped is not None and stamped != root:
        raise AdmissionError(f"{prev_dir}: predecessor no longer matches "
                             "its stamp")
    if manifest.get("previous") != root:
        raise AdmissionError("manifest.previous does not name the "
                             f"predecessor's content ({root})")

    kind, agreement = manifest.get("kind"), {}
    if kind == "language":
        old_i = os.path.join(prev_dir, "interp.py")
        new_i = _reference(entry_dir, "interp.py")
        runs = []
        for prog in _items(prev_dir, "vectors", "program"):
            runs.append(("vectors", prog, prog[:-len(".program")] + ".input"))
        empty = _tmp(b"{}", ".input")
        for pid in sorted(reg["pairs"]):
            pm = reg["pairs"][pid]
            if "admission" not in pm or key not in (pm["src"], pm["tgt"]):
                continue
            for prog in _items(pm["_dir"], "corpus", "program"):
                inp = prog[:-len(".program")] + ".input"
                runs.append(("pair_corpus", prog,
                             inp if os.path.exists(inp) else empty))
        if not runs:
            raise AdmissionError("nothing to agree on — the predecessor "
                                 "has no vectors")
        for label, prog, inp in runs:
            if (_agree_run(old_i, [prog, inp], wall_s)
                    != _agree_run(new_i, [prog, inp], wall_s)):
                raise AdmissionError(
                    f"revision disagrees with its predecessor on "
                    f"{os.path.basename(prog)}")
            agreement[label] = agreement.get(label, 0) + 1
    elif kind == "pair":
        old_t = os.path.join(prev_dir, "T.py")
        new_t = _reference(entry_dir, "T.py")
        corpus = _items(prev_dir, "corpus", "program")
        if not corpus:
            raise AdmissionError("nothing to agree on — the predecessor "
                                 "has no corpus")
        for prog in corpus:
            if (_agree_run(old_t, [prog], wall_s)
                    != _agree_run(new_t, [prog], wall_s)):
                raise AdmissionError(
                    f"revision disagrees with its predecessor on "
                    f"{os.path.basename(prog)}")
        agreement["corpus"] = len(corpus)
    elif kind == "terminal":
        old_s = os.path.join(prev_dir, "solve.py")
        new_s = _reference(entry_dir, "solve.py")
        corpus = _items(prev_dir, "corpus", "program")
        if not corpus:
            raise AdmissionError("nothing to agree on — the predecessor "
                                 "has no corpus")
        for prog in corpus:
            q = json.load(open(prog[:-len(".program")] + ".q",
                               encoding="utf-8"))
            args = [prog, q["mode"], q["observable"], str(q["bound"]),
                    str(wall_s)]
            if (_agree_run(old_s, args, wall_s * 2 + 10)
                    != _agree_run(new_s, args, wall_s * 2 + 10)):
                raise AdmissionError(
                    f"revision disagrees with its predecessor on "
                    f"{os.path.basename(prog)}")
        agreement["corpus"] = len(corpus)
    return {"revision": rev, "previous": root, "agreement": agreement}


# -- interpretation helpers (shared with the driver) --------------------------

def interpret(script: str, program: str, input_path: str,
              wall_s: float = _DEFAULT_WALL_S) -> dict:
    """Run a language's interpreter deterministically; return observables."""
    res, same = runner.run_twice(script, [program, input_path], wall_s=wall_s)
    if not same:
        raise AdmissionError(f"{script}: nondeterministic or timed out")
    return _json_out(res, script)


def certify_witness(lang_manifest: dict, terminal_dir: str, program: str,
                    observable: str, payload, *,
                    hops: list[dict] | None = None,
                    programs: list[str] | None = None,
                    wall_s: float = _DEFAULT_WALL_S) -> tuple[bool, int]:
    """Existential certification: Λ then source interpretation.

    The terminal's ``lam.py`` turns the witness payload into an
    interpreter input; each translation hop's ``lam.py`` (reverse order)
    carries the input one language back; the source interpreter — the
    Python reference, always — replays. Every ``lam.py`` also receives
    the program at its own source side (``programs`` is the route's
    program chain, source first) — a carry-back that must decode against
    the system, like a model becoming a machine binding, reads it from
    there. Returns (fired, depth). Fail-safe: any error refutes the
    *witness*, never the answer.
    """
    try:
        programs = programs or [program]
        payload_path = _tmp(json.dumps(payload, sort_keys=True).encode(),
                            ".payload")
        input_path = payload_path
        lam = os.path.join(terminal_dir, "lam.py")
        if os.path.exists(lam):
            res, same = runner.run_twice(lam, [input_path, programs[-1]],
                                         wall_s=wall_s)
            if not same or not res.ok:
                return False, 0
            input_path = _tmp(res.out, ".input")
        for i, hop in reversed(list(enumerate(hops or []))):
            hop_lam = os.path.join(hop["_dir"], "lam.py")
            if not os.path.exists(hop_lam):
                return False, 0        # witnesses cannot cross this hop
            res, same = runner.run_twice(
                hop_lam, [input_path,
                          programs[i] if i < len(programs) else program],
                wall_s=wall_s)
            if not same or not res.ok:
                return False, 0
            input_path = _tmp(res.out, ".input")
        interp = os.path.join(lang_manifest["_dir"], "interp.py")
        obs = interpret(interp, program, input_path, wall_s)
        return bool(obs.get(observable)), int(obs.get("depth", 0))
    except AdmissionError:
        return False, 0


def discharge_cert(terminal_dir: str, program: str, cert, *,
                   wall_s: float = _DEFAULT_WALL_S) -> dict | None:
    """Universal certification: run the terminal's certifier on
    (program, certificate). Returns the obligations record on a
    validated discharge, ``None`` otherwise. Fail-safe direction
    (KERNEL.md §3): a wrong or wrongly-mapped certificate — or a
    missing, nondeterministic, or crashing certifier — can only fail to
    upgrade, never fake a certification."""
    script = os.path.join(terminal_dir, "discharge.py")
    if cert is None or not os.path.exists(script):
        return None
    cert_path = _tmp(json.dumps(cert, sort_keys=True).encode(), ".cert")
    res, same = runner.run_twice(script, [program, cert_path],
                                 wall_s=wall_s)
    if not same or not res.ok:
        return None
    try:
        out = json.loads(res.out)
    except json.JSONDecodeError:
        return None
    if out.get("ok") is not True:
        return None
    return out.get("obligations", {})


# -- language admission -------------------------------------------------------

def _run_vectors(lang_dir: str, interp: str, wall_s: float) -> int:
    vectors = _items(lang_dir, "vectors", "program")
    for prog in vectors:
        stem = prog[:-len(".program")]
        expect = json.load(open(stem + ".expect", encoding="utf-8"))
        obs = interpret(interp, prog, stem + ".input", wall_s)
        for k, v in expect.items():
            if obs.get(k) != v:
                raise AdmissionError(f"{interp} on {os.path.basename(prog)}: "
                                     f"{k}={obs.get(k)!r}, expected {v!r}")
    return len(vectors)


def check_language(lang_dir: str, manifest: dict, *,
                   wall_s: float = _DEFAULT_WALL_S) -> dict:
    lang_dir = os.path.abspath(lang_dir)
    _no_accelerator(lang_dir, manifest)
    interp = _reference(lang_dir, "interp.py")
    n = _run_vectors(lang_dir, interp, wall_s)
    if n == 0:
        raise AdmissionError(f"{lang_dir}: no vectors — nothing checked")
    mutants = _mutants(lang_dir)
    if not mutants:
        raise AdmissionError(f"{lang_dir}: no negative controls — "
                             "an uncheckable checker is unfalsifiable")
    for mutant in mutants:
        try:
            _run_vectors(lang_dir, mutant, wall_s)
        except AdmissionError:
            continue                       # the control failed: good
        raise AdmissionError(f"{mutant} passed the vectors — "
                             "the vectors cannot catch a defect")
    return {"checked": "language", "vectors": n, "controls": len(mutants)}


# -- pair admission -----------------------------------------------------------

def _compare(direction: str, keeps: list[str], src_obs: dict,
             carried: dict) -> str | None:
    """None if the square holds on the kept observables, else a message."""
    for k in keeps:
        s, t = src_obs.get(k), carried.get(k)
        if direction == "exact":
            ok = s == t
        elif direction == "over":       # target may have more behaviors
            ok = (s == t) if not isinstance(s, bool) else (t or not s)
        elif direction == "under":
            ok = (s == t) if not isinstance(s, bool) else (s or not t)
        else:
            return f"unknown direction {direction!r}"
        if not ok:
            return f"square broken on {k!r}: source {s!r}, carried {t!r}"
    return None


def _square(pair_dir: str, translate: str, manifest: dict, src_lang: dict,
            tgt_lang: dict, prog: str, input_path: str,
            wall_s: float) -> str | None:
    res, same = runner.run_twice(translate, [prog], wall_s=wall_s)
    if not same:
        return f"{translate}: nondeterministic or timed out"
    if not res.ok:
        return f"{translate}: rc={res.rc} err={res.err[:200]!r}"
    tgt_prog = _tmp(res.out, ".program")
    src_obs = interpret(os.path.join(src_lang["_dir"], "interp.py"),
                        prog, input_path, wall_s)
    tgt_obs = interpret(os.path.join(tgt_lang["_dir"], "interp.py"),
                        tgt_prog, input_path, wall_s)
    # Λ on observables (I_s ≡π Λ(I_t(T(p)))): a pair whose languages
    # name their observables differently carries the target behavior
    # back before the comparison. Its honesty is not assumed: every
    # translator mutant must still break the square *through* it, so a
    # carry-back that flattens or invents observables is itself caught
    # by the two-sided controls. The manifest's declarative ``maps``
    # (source name -> target name) is what routing composes; when a
    # lam_obs.py is also shipped the two must agree per program, and
    # when it is not, the renaming ``maps`` declares *is* the Λ.
    lam_obs = os.path.join(pair_dir, "lam_obs.py")
    maps = manifest.get("maps") or {}
    carried = tgt_obs
    if os.path.exists(lam_obs):
        obs_path = _tmp(json.dumps(tgt_obs, sort_keys=True).encode(),
                        ".obs")
        res, same = runner.run_twice(lam_obs, [obs_path], wall_s=wall_s)
        if not same:
            return f"{lam_obs}: nondeterministic or timed out"
        if not res.ok:
            return f"{lam_obs}: rc={res.rc} err={res.err[:200]!r}"
        carried = _json_out(res, lam_obs)
        for src_name, tgt_name in maps.items():
            if carried.get(src_name) != tgt_obs.get(tgt_name):
                return (f"declared map {src_name!r}->{tgt_name!r} "
                        "disagrees with lam_obs on this program")
    elif maps:
        carried = dict(tgt_obs)
        for src_name, tgt_name in maps.items():
            carried[src_name] = tgt_obs.get(tgt_name)
    return _compare(manifest["direction"], manifest["keeps"], src_obs,
                    carried)


def check_pair(reg: dict, pair_dir: str, manifest: dict, *,
               wall_s: float = _DEFAULT_WALL_S) -> dict:
    pair_dir = os.path.abspath(pair_dir)
    src = reg["languages"][manifest["src"]]
    tgt = reg["languages"][manifest["tgt"]]
    corpus = _items(pair_dir, "corpus", "program")
    if not corpus:
        raise AdmissionError(f"{pair_dir}: empty corpus")
    empty = _tmp(b"{}", ".input")
    inputs = {p: (p[:-len('.program')] + ".input"
                  if os.path.exists(p[:-len('.program')] + ".input")
                  else empty) for p in corpus}
    translate = _reference(pair_dir, "T.py")
    for prog in corpus:
        msg = _square(pair_dir, translate, manifest, src, tgt, prog,
                      inputs[prog], wall_s)
        if msg:
            raise AdmissionError(f"{os.path.basename(prog)}: {msg}")
    mutants = _mutants(pair_dir)
    if not mutants:
        raise AdmissionError(f"{pair_dir}: no negative controls")
    for mutant in mutants:
        broken = any(
            _square(pair_dir, mutant, manifest, src, tgt, prog, inputs[prog],
                    wall_s) for prog in corpus)
        if not broken:
            raise AdmissionError(f"{mutant} passed the square — "
                                 "the corpus cannot catch a defect")
    evidence = {"checked": "pair", "corpus": len(corpus),
                "controls": len(mutants)}
    acc = _check_accelerator(pair_dir, manifest,
                             [[prog] for prog in corpus], wall_s)
    if acc is not None:
        evidence["accelerator"] = acc
    return evidence


# -- terminal admission -------------------------------------------------------

def _solve(script: str, prog: str, q: dict, wall_s: float) -> dict:
    res, same = runner.run_twice(
        script, [prog, q["mode"], q["observable"], str(q["bound"]),
                 str(wall_s)], wall_s=wall_s * 2 + 10)
    if not same:
        raise AdmissionError(f"{script}: nondeterministic or timed out")
    return _json_out(res, script)


def _terminal_corpus_ok(reg: dict, term_dir: str, manifest: dict, solve: str,
                        wall_s: float) -> tuple[int, int, str | None]:
    """Every non-partial verdict must match its label, every witness
    must replay, and every emitted certificate must discharge; at least
    one non-partial result is required (a terminal that only abstains is
    vacuous). Returns (corpus size, certificates discharged, a program
    whose certificate discharged — the anvil for the cert mutants)."""
    lang = reg["languages"][manifest["language"]]
    corpus = _items(term_dir, "corpus", "program")
    if not corpus:
        raise AdmissionError(f"{term_dir}: empty corpus")
    decided, discharged, cert_prog = 0, 0, None
    for prog in corpus:
        q = json.load(open(prog[:-len(".program")] + ".q", encoding="utf-8"))
        name = os.path.basename(prog)
        if q["observable"] not in manifest["decides"]:
            raise AdmissionError(f"{name}: asks {q['observable']!r}, not "
                                 f"among decides {manifest['decides']}")
        value = _solve(solve, prog, q, wall_s)
        if value["kind"] == "witness":
            fired, _ = certify_witness(lang, term_dir, prog, q["observable"],
                                       value.get("payload"), wall_s=wall_s)
            if not fired:
                raise AdmissionError(f"{name}: witness did not replay")
            if q.get("label") is False:
                raise AdmissionError(f"{name}: witness against label=false")
            decided += 1
        elif value["kind"] == "all":
            if q.get("label") is True and results.covers(value["bound"],
                                                         q["bound"]):
                raise AdmissionError(f"{name}: all({value['bound']}) against "
                                     "label=true")
            if value.get("cert") is not None:
                if discharge_cert(term_dir, prog, value["cert"],
                                  wall_s=wall_s) is None:
                    raise AdmissionError(f"{name}: certificate did not "
                                         "discharge")
                discharged += 1
                cert_prog = cert_prog or prog
            decided += 1
        elif value["kind"] != "partial":
            raise AdmissionError(f"{name}: unknown value kind "
                                 f"{value['kind']!r}")
    if decided == 0:
        raise AdmissionError(f"{term_dir}: terminal abstained on the whole "
                             "corpus — vacuous")
    return len(corpus), discharged, cert_prog


def check_terminal(reg: dict, term_dir: str, manifest: dict, *,
                   wall_s: float = _DEFAULT_WALL_S) -> dict:
    term_dir = os.path.abspath(term_dir)
    solve = _reference(term_dir, "solve.py")
    n, discharged, cert_prog = _terminal_corpus_ok(reg, term_dir, manifest,
                                                   solve, wall_s)
    mutants = _mutants(term_dir)
    if not mutants:
        raise AdmissionError(f"{term_dir}: no negative controls")
    for mutant in mutants:
        try:
            _terminal_corpus_ok(reg, term_dir, manifest, mutant, wall_s)
        except AdmissionError:
            continue
        raise AdmissionError(f"{mutant} passed the corpus — "
                             "the corpus cannot catch a defect")
    evidence = {"checked": "terminal", "corpus": n, "controls": len(mutants)}
    if os.path.exists(os.path.join(term_dir, "discharge.py")):
        if discharged == 0:
            raise AdmissionError(f"{term_dir}: certifier never "
                                 "exercised — no corpus certificate")
        cert_mutants = sorted(glob.glob(os.path.join(
            term_dir, "controls", "cert_mutant_*.json")))
        if not cert_mutants:
            raise AdmissionError(f"{term_dir}: no certificate negative "
                                 "controls — an uncheckable certifier is "
                                 "unfalsifiable")
        for cm in cert_mutants:
            cert = json.load(open(cm, encoding="utf-8"))
            if discharge_cert(term_dir, cert_prog, cert,
                              wall_s=wall_s) is not None:
                raise AdmissionError(f"{cm} discharged — the certifier "
                                     "cannot catch a wrong certificate")
        evidence["cert_mutants"] = len(cert_mutants)
        evidence["discharged"] = discharged
    invocations = []
    for prog in _items(term_dir, "corpus", "program"):
        q = json.load(open(prog[:-len(".program")] + ".q", encoding="utf-8"))
        invocations.append([prog, q["mode"], q["observable"],
                            str(q["bound"]), str(wall_s)])
    acc = _check_accelerator(term_dir, manifest, invocations, wall_s)
    if acc is not None:
        evidence["accelerator"] = acc
    return evidence


# -- domain admission ---------------------------------------------------------

def check_domain(dom_dir: str, manifest: dict) -> dict:
    """A domain is the ungenerable half: a root language's name and the
    anchors that corroborate its interpreter. Nothing executes — but the
    anchors must be stated, because a domain without ground truth could
    never grade past stipulated. The root need not be admitted yet: the
    domain enters with the benchmark, and writing the root's interpreter
    is the loop's first act (KERNEL.md §6)."""
    _no_accelerator(dom_dir, manifest)
    if not isinstance(manifest.get("root"), str) or not manifest["root"]:
        raise AdmissionError(f"{dom_dir}: no root language named")
    anchors = manifest.get("anchors")
    if not isinstance(anchors, list) or not anchors:
        raise AdmissionError(f"{dom_dir}: no anchors — a domain enters "
                             "with its ground truth stated")
    return {"checked": "domain", "anchors": len(anchors)}


# -- the dispatch -------------------------------------------------------------

def check(reg: dict, entry_dir: str, manifest: dict, *,
          wall_s: float = _DEFAULT_WALL_S) -> dict:
    """The one gate: every kind, one discipline, evidence returned for
    the stamp — or an AdmissionError saying exactly where it failed.
    A revision first passes the conservativity gate against its
    predecessor, then the ordinary kind gate like any first
    admission; the stamp carries both."""
    entry_dir = os.path.abspath(entry_dir)
    revision = _check_revision(reg, entry_dir, manifest, wall_s)
    kind = manifest.get("kind")
    if kind == "language":
        evidence = check_language(entry_dir, manifest, wall_s=wall_s)
    elif kind == "pair":
        evidence = check_pair(reg, entry_dir, manifest, wall_s=wall_s)
    elif kind == "terminal":
        evidence = check_terminal(reg, entry_dir, manifest, wall_s=wall_s)
    elif kind == "domain":
        evidence = check_domain(entry_dir, manifest)
    else:
        raise AdmissionError(f"unknown kind {kind!r}")
    if revision is not None:
        evidence.update(revision)
    return evidence
