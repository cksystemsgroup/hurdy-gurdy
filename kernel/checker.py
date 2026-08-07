"""Admission — the one gate (KERNEL.md §§1–2, §9).

One discipline for every artifact: determinism is measured (run twice,
byte-compare), the checkable relation is run on the entry's own corpus,
and controls are two-sided — the intact artifact must pass and every
supplied mutant must fail. A checker that cannot be made to fail is
unfalsifiable, not checked; admission therefore *requires* at least one
vector/corpus item and at least one mutant.

Conventions inside an entry directory:

- language:  ``interp.py <program> <input>`` -> observables JSON;
  ``vectors/NNN.{program,input,expect}``; ``controls/mutant_*.py``.
- translation pair: ``T.py <program>`` -> target program;
  ``lam.py <input>`` -> source input (carries behaviors back; optional,
  but witnesses cannot cross a hop without it);
  ``lam_obs.py <target-obs-json>`` -> source observables (optional: the
  square's Λ on observables, for pairs whose languages name their
  observables differently — absent, Λ is the identity and both sides
  must emit the same keys); ``corpus/NNN.program`` (+ ``NNN.input``);
  ``controls/mutant_*.py``.
- solver pair: ``solve.py <program> <mode> <observable> <bound> <wall_s>``
  -> result-value JSON; ``lam.py <witness-payload>`` -> interpreter
  input; ``corpus/NNN.{program,q}`` with labels; ``controls/mutant_*.py``.
  Optionally ``discharge.py <program> <cert-file>`` ->
  ``{"ok": bool, "obligations": {...}}``: the certificate checker the
  kernel runs on every ``all`` value carrying a ``cert`` (KERNEL.md §2 —
  certified at the source, checked past translation hops, claimed on any
  failure). A pair that ships one must exercise it during admission
  (some corpus certificate must discharge) and must supply
  ``controls/cert_mutant_*.json`` certificates that fail to.
"""

from __future__ import annotations

import glob
import json
import os
import tempfile

from . import results, runner

_DEFAULT_WALL_S = 60.0


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


# -- interpretation helpers (shared with the driver) --------------------------

def interpret(lang_manifest: dict, script: str, program: str, input_path: str,
              wall_s: float = _DEFAULT_WALL_S) -> dict:
    """Run a language's interpreter deterministically; return observables."""
    res, same = runner.run_twice(script, [program, input_path], wall_s=wall_s)
    if not same:
        raise AdmissionError(f"{script}: nondeterministic or timed out")
    return _json_out(res, script)


def certify_witness(lang_manifest: dict, pair_dir: str, program: str,
                    observable: str, payload, *,
                    hops: list[dict] | None = None,
                    wall_s: float = _DEFAULT_WALL_S) -> tuple[bool, int]:
    """Existential certification: Λ then source interpretation.

    The solver pair's ``lam.py`` turns the witness payload into an
    interpreter input; each translation hop's ``lam.py`` (reverse order)
    carries the input one language back; the source interpreter replays.
    Returns (fired, depth). Fail-safe: any error refutes the *witness*,
    never the answer.
    """
    try:
        payload_path = _tmp(json.dumps(payload, sort_keys=True).encode(),
                            ".payload")
        input_path = payload_path
        lam = os.path.join(pair_dir, "lam.py")
        if os.path.exists(lam):
            res, same = runner.run_twice(lam, [input_path], wall_s=wall_s)
            if not same or not res.ok:
                return False, 0
            input_path = _tmp(res.out, ".input")
        for hop in reversed(hops or []):
            hop_lam = os.path.join(hop["_dir"], "lam.py")
            if not os.path.exists(hop_lam):
                return False, 0        # witnesses cannot cross this hop
            res, same = runner.run_twice(hop_lam, [input_path],
                                         wall_s=wall_s)
            if not same or not res.ok:
                return False, 0
            input_path = _tmp(res.out, ".input")
        interp = os.path.join(lang_manifest["_dir"], "interp.py")
        obs = interpret(lang_manifest, interp, program, input_path, wall_s)
        return bool(obs.get(observable)), int(obs.get("depth", 0))
    except AdmissionError:
        return False, 0


def discharge_cert(pair_dir: str, program: str, cert, *,
                   wall_s: float = _DEFAULT_WALL_S) -> dict | None:
    """Universal certification: run the pair's discharge checker on
    (program, certificate). Returns the obligations record on a
    validated discharge, ``None`` otherwise. Fail-safe direction
    (KERNEL.md §2): a wrong or wrongly-mapped certificate — or a
    missing, nondeterministic, or crashing checker — can only fail to
    upgrade, never fake a certification."""
    script = os.path.join(pair_dir, "discharge.py")
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
        obs = interpret({}, interp, prog, stem + ".input", wall_s)
        for k, v in expect.items():
            if obs.get(k) != v:
                raise AdmissionError(f"{interp} on {os.path.basename(prog)}: "
                                     f"{k}={obs.get(k)!r}, expected {v!r}")
    return len(vectors)


def check_language(lang_dir: str, *,
                   wall_s: float = _DEFAULT_WALL_S) -> dict:
    lang_dir = os.path.abspath(lang_dir)
    interp = os.path.join(lang_dir, "interp.py")
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


# -- translation-pair admission ----------------------------------------------

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
    src_obs = interpret(src_lang, os.path.join(src_lang["_dir"], "interp.py"),
                        prog, input_path, wall_s)
    tgt_obs = interpret(tgt_lang, os.path.join(tgt_lang["_dir"], "interp.py"),
                        tgt_prog, input_path, wall_s)
    # Λ on observables (I_s ≡π Λ(I_t(T(p)))): a pair whose languages
    # name their observables differently carries the target behavior
    # back before the comparison. Its honesty is not assumed: every
    # translator mutant must still break the square *through* it, so a
    # carry-back that flattens or invents observables is itself caught
    # by the two-sided controls.
    lam_obs = os.path.join(pair_dir, "lam_obs.py")
    if os.path.exists(lam_obs):
        obs_path = _tmp(json.dumps(tgt_obs, sort_keys=True).encode(),
                        ".obs")
        res, same = runner.run_twice(lam_obs, [obs_path], wall_s=wall_s)
        if not same:
            return f"{lam_obs}: nondeterministic or timed out"
        if not res.ok:
            return f"{lam_obs}: rc={res.rc} err={res.err[:200]!r}"
        tgt_obs = _json_out(res, lam_obs)
    return _compare(manifest["direction"], manifest["keeps"], src_obs,
                    tgt_obs)


def check_translation_pair(reg: dict, pair_dir: str, manifest: dict, *,
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
    translate = os.path.join(pair_dir, "T.py")
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
    return {"checked": "translation", "corpus": len(corpus),
            "controls": len(mutants)}


# -- solver-pair admission ----------------------------------------------------

def _solve(script: str, prog: str, q: dict, wall_s: float) -> dict:
    res, same = runner.run_twice(
        script, [prog, q["mode"], q["observable"], str(q["bound"]),
                 str(wall_s)], wall_s=wall_s * 2 + 10)
    if not same:
        raise AdmissionError(f"{script}: nondeterministic or timed out")
    return _json_out(res, script)


def _solver_corpus_ok(reg: dict, pair_dir: str, manifest: dict, solve: str,
                      wall_s: float) -> tuple[int, int, str | None]:
    """Every non-partial verdict must match its label, every witness
    must replay, and every emitted certificate must discharge; at least
    one non-partial result is required (a solver that only abstains is
    vacuous). Returns (corpus size, certificates discharged, a program
    whose certificate discharged — the anvil for the cert mutants)."""
    src = reg["languages"][manifest["src"]]
    corpus = _items(pair_dir, "corpus", "program")
    if not corpus:
        raise AdmissionError(f"{pair_dir}: empty corpus")
    decided, discharged, cert_prog = 0, 0, None
    for prog in corpus:
        q = json.load(open(prog[:-len(".program")] + ".q", encoding="utf-8"))
        value = _solve(solve, prog, q, wall_s)
        name = os.path.basename(prog)
        if value["kind"] == "witness":
            fired, _ = certify_witness(src, pair_dir, prog, q["observable"],
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
                if discharge_cert(pair_dir, prog, value["cert"],
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
        raise AdmissionError(f"{pair_dir}: solver abstained on the whole "
                             "corpus — vacuous")
    return len(corpus), discharged, cert_prog


def check_solver_pair(reg: dict, pair_dir: str, manifest: dict, *,
                      wall_s: float = _DEFAULT_WALL_S) -> dict:
    pair_dir = os.path.abspath(pair_dir)
    solve = os.path.join(pair_dir, "solve.py")
    n, discharged, cert_prog = _solver_corpus_ok(reg, pair_dir, manifest,
                                                 solve, wall_s)
    mutants = _mutants(pair_dir)
    if not mutants:
        raise AdmissionError(f"{pair_dir}: no negative controls")
    for mutant in mutants:
        try:
            _solver_corpus_ok(reg, pair_dir, manifest, mutant, wall_s)
        except AdmissionError:
            continue
        raise AdmissionError(f"{mutant} passed the corpus — "
                             "the corpus cannot catch a defect")
    evidence = {"checked": "solver", "corpus": n, "controls": len(mutants)}
    if os.path.exists(os.path.join(pair_dir, "discharge.py")):
        if discharged == 0:
            raise AdmissionError(f"{pair_dir}: discharge checker never "
                                 "exercised — no corpus certificate")
        cert_mutants = sorted(glob.glob(os.path.join(
            pair_dir, "controls", "cert_mutant_*.json")))
        if not cert_mutants:
            raise AdmissionError(f"{pair_dir}: no certificate negative "
                                 "controls — an uncheckable discharge is "
                                 "unfalsifiable")
        for cm in cert_mutants:
            cert = json.load(open(cm, encoding="utf-8"))
            if discharge_cert(pair_dir, cert_prog, cert,
                              wall_s=wall_s) is not None:
                raise AdmissionError(f"{cm} discharged — the checker cannot "
                                     "catch a wrong certificate")
        evidence["cert_mutants"] = len(cert_mutants)
        evidence["discharged"] = discharged
    return evidence


def check_pair(reg: dict, pair_dir: str, manifest: dict, *,
               wall_s: float = _DEFAULT_WALL_S) -> dict:
    if manifest.get("pair_kind") == "solver":
        return check_solver_pair(reg, pair_dir, manifest, wall_s=wall_s)
    return check_translation_pair(reg, pair_dir, manifest, wall_s=wall_s)
