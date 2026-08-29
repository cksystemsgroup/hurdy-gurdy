"""Admission — the one gate (KERNEL.md §10).

One discipline for every entry: determinism is measured (run twice,
byte-compare), the checkable relation is run on the entry's own corpus,
and controls are two-sided — the intact implementation must pass and
every supplied mutant must fail. A checker that cannot be made to fail
is unfalsifiable, not checked; admission therefore *requires* at least
one vector/corpus item and at least one mutant per checked executable.

For a pair the checkable relation is per channel (KERNEL.md §2, §10):
**every declared channel round-trips per corpus program** — squares
close (`prog`), stimuli replay (`wit`), certificates re-discharge
(`cert`) — with mutants supplied per channel. Every arrival check is
an interpreter run; the judges are the languages', never the pair's.

The generation rule (KERNEL.md §6) is enforced here and in the sealed
runner: every reference implementation the gate runs must be generated
Python living inside the entry — there are no existing tools to wrap,
and the sandbox has no environment to find one in. An entry may ship
one **accelerator** — the same implementation in a performance-oriented
language — and only for the per-play transports ``T.py`` and
``solve.py``, whose outputs face judges downstream; it is admitted
solely by byte-agreement with the Python reference on every admission
invocation, and the reference remains the semantics. Judges —
interpreters and evidence checkers — and the carry-backs the checks
run through are never accelerated.

Conventions inside an entry directory:

- language:  ``interp.py <program> <input>`` -> observables JSON;
  ``vectors/NNN.{program,input,expect}``; ``controls/mutant_*.py``
  (interpreter mutants that must fail the vectors). Certificate
  judges under ``evidence/<schema>/``: ``check.py <program>
  <cert-file>`` -> ``{"ok": bool, "obligations": {...}}``;
  ``vectors/NNN.{program,cert}`` (must discharge);
  ``controls/NNN.cert`` (mutant certificates, judged against
  ``vectors/NNN.program``, that must fail). The witness schema is
  free: its judge is ``interp.py`` itself — replay.
- pair: manifest declares ``channels``; ``prog`` is required and
  ``T.py <program>`` -> target program is its transport. Optional
  per channel: ``lam_wit.py <target-input> <src-program>`` -> source
  input (`wit`; direction exact/under only); ``lam_cert.py
  <target-cert> <src-program>`` -> source certificate
  ``{"schema", "payload"}`` (`cert`; direction exact/over only);
  ``lam_obs.py <target-obs-json>`` -> source observables (`obs`,
  else the declarative ``maps`` renaming is the carry-back);
  ``hint.py <src-program>`` -> seeds JSON (`hint`; trust-inert, so
  determinism is its whole gate). ``claim`` has no executable — the
  checkless channel (direction exact/over; ``bound_cap`` optional).
  Corpus: ``NNN.program`` (+ ``NNN.input`` source stimulus,
  ``NNN.wit`` target stimulus, ``NNN.cert`` target certificate).
  Controls per channel: ``prog_mutant_*.py`` (a broken T),
  ``wit_mutant_*.py`` (a broken lam_wit), ``cert_mutant_*.py``
  (a broken lam_cert) — each must fail its channel's round-trip.
- search: ``solve.py <program> <mode> <observable> <bound> <wall_s>
  [<hints-file>]`` -> result-value JSON, where a certificate is
  ``{"schema": <name>, "payload": ...}`` judged by the search's own
  language; ``corpus/NNN.{program,q}`` with labels;
  ``controls/mutant_*.py``. Optional ``ledger.py <program>
  <value-file>`` -> ledger JSON (KERNEL.md §5: surprisal bounds,
  cleared bits — profiling recorded beside the path, never ranked,
  never a grade; trust-inert, so determinism is its whole gate).
- domain: manifest only — the root language's name and the non-empty
  anchors (labels, supplied vectors, recorded oracle testimony): the
  ungenerable half.
"""

from __future__ import annotations

import glob
import json
import os
import tempfile

from . import registry, results, runner

_DEFAULT_WALL_S = 60.0

#: The only executables an accelerator may replace: the per-play
#: transports, whose outputs face judges downstream (KERNEL.md §6).
_ACCELERABLE = ("T.py", "solve.py")

#: The six channels (KERNEL.md §2) and each one's executable, where it
#: has one. ``claim`` is the checkless channel; ``obs`` rides ``maps``
#: unless a ``lam_obs.py`` is shipped.
_CHANNELS = ("prog", "wit", "obs", "claim", "cert", "hint")
_CHANNEL_EXE = {"prog": "T.py", "wit": "lam_wit.py", "cert": "lam_cert.py",
                "hint": "hint.py"}
#: Which directions may carry each backward channel (KERNEL.md §2):
#: witnesses cross back along exact and under hops; universal objects
#: (claims and certificates) along exact and over.
_CHANNEL_DIRECTIONS = {"wit": ("exact", "under"),
                       "claim": ("exact", "over"),
                       "cert": ("exact", "over")}


class AdmissionError(Exception):
    """The entry failed admission; the message says exactly where."""


def _items(entry_dir: str, sub: str, ext: str) -> list[str]:
    return sorted(glob.glob(os.path.join(entry_dir, sub, f"*.{ext}")))


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
    """The performance seam (KERNEL.md §6): one accelerator per entry,
    the per-play transports only, admitted by byte-agreement with the
    Python reference on every admission invocation. The reference
    remains the semantics; the accelerator is only ever a cheaper way
    to the same bytes — and whatever it emits at play time is still
    judged downstream (witnesses replay, universal objects grade)."""
    acc = manifest.get("accelerator")
    if acc is None:
        return None
    for field in ("replaces", "exe", "source", "language"):
        if field not in acc:
            raise AdmissionError(f"accelerator missing {field!r}")
    if acc["replaces"] not in _ACCELERABLE:
        raise AdmissionError(
            f"accelerator may replace only {_ACCELERABLE} — judging "
            "(interpretation, discharge) and the carry-backs stay "
            "reference Python")
    exe = os.path.join(entry_dir, acc["exe"])
    if not os.path.isfile(exe):
        raise AdmissionError(f"accelerator exe missing: {acc['exe']}")
    if not os.path.isfile(os.path.join(entry_dir, acc["source"])):
        raise AdmissionError(f"accelerator source missing: {acc['source']} "
                             "— the generated text is part of the entry")
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


# -- the judges (arrival checks are interpreter runs, nothing else) -----------

def interpret(script: str, program: str, input_path: str,
              wall_s: float = _DEFAULT_WALL_S) -> dict:
    """Run a language's interpreter deterministically; return observables."""
    res, same = runner.run_twice(script, [program, input_path], wall_s=wall_s)
    if not same:
        raise AdmissionError(f"{script}: nondeterministic or timed out")
    return _json_out(res, script)


def replay(lang_manifest: dict, program: str, observable: str, payload, *,
           wall_s: float = _DEFAULT_WALL_S) -> tuple[bool, int]:
    """The witness judge — the language's own interpreter, no generated
    code between the payload and the trust event. Returns (fired,
    depth). Fail-safe: any error refutes the *witness*, never the
    answer."""
    try:
        input_path = _tmp(json.dumps(payload, sort_keys=True).encode(),
                          ".input")
        interp = os.path.join(lang_manifest["_dir"], "interp.py")
        obs = interpret(interp, program, input_path, wall_s)
        return bool(obs.get(observable)), int(obs.get("depth", 0))
    except AdmissionError:
        return False, 0


def discharge(lang_manifest: dict, program: str, cert, *,
              wall_s: float = _DEFAULT_WALL_S) -> dict | None:
    """The certificate judge — dispatch into the language's own
    evidence checker, named by the certificate's schema (KERNEL.md §3:
    ``Evidence(L)`` is induced, never written). Returns the obligations
    record on a validated discharge, ``None`` otherwise. Fail-safe
    direction: a wrong or wrongly-carried certificate — or a missing,
    nondeterministic, or crashing checker — can only fail to upgrade,
    never fake a check."""
    if not isinstance(cert, dict) or "schema" not in cert:
        return None
    script = os.path.join(lang_manifest["_dir"], "evidence",
                          str(cert["schema"]), "check.py")
    if not os.path.isfile(script):
        return None
    cert_path = _tmp(json.dumps(cert.get("payload"),
                                sort_keys=True).encode(), ".cert")
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


# -- revision, not mutation ---------------------------------------------------

def _agree_run(script: str, args: list[str], wall_s: float) -> bytes:
    res, same = runner.run_twice(script, args, wall_s=wall_s)
    if not same or not res.ok:
        raise AdmissionError(f"{script}: failed or nondeterministic while "
                             "replaying the revision agreement")
    return res.out


def _agree(old: str, new: str, args: list[str], wall_s: float,
           what: str) -> None:
    if _agree_run(old, args, wall_s) != _agree_run(new, args, wall_s):
        raise AdmissionError(f"revision disagrees with its predecessor "
                             f"on {what}")


def _check_revision(reg: dict, entry_dir: str, manifest: dict,
                    wall_s: float) -> dict | None:
    """The conservativity gate (KERNEL.md §10): a revision is admitted
    against its predecessor. The predecessor must exist, be admitted,
    and still match its content pin; the manifest's ``previous`` must
    name that exact content; and the new implementation must
    byte-agree with the old on the old entry's checkable surface —
    its vectors or corpus, plus (for a language) its evidence judges
    on their vectors and the corpora of every admitted pair bound to
    it. Agreement is what lets dependent stamps keep their meaning;
    the new fragment is then checked by the ordinary kind gate like
    any first admission. Adding a channel to an admitted pair is the
    intended common case: the old channels are the conserved surface,
    the new channel is gated fresh."""
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

    def count(label: str) -> None:
        agreement[label] = agreement.get(label, 0) + 1

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
                inp = inp if os.path.exists(inp) else empty
                if pm["src"] == key:
                    runs.append(("pair_corpus", prog, inp))
                else:
                    # bound as target only: the corpus lives in the
                    # pair's *source* language, so the pair's evidence
                    # in this language is its translated corpus — the
                    # side its admitted squares checked (always the
                    # Python reference T, never an accelerator)
                    out = _agree_run(os.path.join(pm["_dir"], "T.py"),
                                     [prog], wall_s)
                    runs.append(("pair_corpus", _tmp(out, ".program"),
                                 inp))
        if not runs:
            raise AdmissionError("nothing to agree on — the predecessor "
                                 "has no vectors")
        for label, prog, inp in runs:
            _agree(old_i, new_i, [prog, inp], wall_s, os.path.basename(prog))
            count(label)
        # the predecessor's evidence judges are part of its checkable
        # surface: every schema it shipped must survive, byte-agreeing
        # on the predecessor's own evidence vectors
        for schema in registry.schemas({"_dir": prev_dir}):
            old_c = os.path.join(prev_dir, "evidence", schema, "check.py")
            new_c = os.path.join(entry_dir, "evidence", schema, "check.py")
            if not os.path.isfile(new_c):
                raise AdmissionError(f"revision drops evidence schema "
                                     f"{schema!r} — a revision that cannot "
                                     "agree is a different tool")
            for prog in _items(os.path.join(prev_dir, "evidence", schema),
                               "vectors", "program"):
                cert = prog[:-len(".program")] + ".cert"
                _agree(old_c, new_c, [prog, cert], wall_s,
                       f"{schema}/{os.path.basename(prog)}")
                count(f"evidence:{schema}")
    elif kind == "pair":
        old_t = os.path.join(prev_dir, "T.py")
        new_t = _reference(entry_dir, "T.py")
        corpus = _items(prev_dir, "corpus", "program")
        if not corpus:
            raise AdmissionError("nothing to agree on — the predecessor "
                                 "has no corpus")
        for prog in corpus:
            _agree(old_t, new_t, [prog], wall_s, os.path.basename(prog))
            count("corpus")
            stem = prog[:-len(".program")]
            for chan, exe in (("wit", "lam_wit.py"), ("cert", "lam_cert.py")):
                old_l = os.path.join(prev_dir, exe)
                art = stem + "." + chan
                if os.path.isfile(old_l) and os.path.exists(art):
                    new_l = _reference(entry_dir, exe)
                    _agree(old_l, new_l, [art, prog], wall_s,
                           os.path.basename(art))
                    count(chan)
    elif kind == "search":
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
            old_out = _agree_run(old_s, args, wall_s * 2 + 10)
            new_out = _agree_run(new_s, args, wall_s * 2 + 10)
            if old_out != new_out:
                raise AdmissionError(
                    f"revision disagrees with its predecessor on "
                    f"{os.path.basename(prog)}")
            count("corpus")
    return {"revision": rev, "previous": root, "agreement": agreement}


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


def _check_evidence_schema(lang_dir: str, schema: str,
                           wall_s: float) -> dict:
    """One certificate judge (KERNEL.md §3, §10): the shipped checker
    must discharge its example certificates and refuse its mutant
    ones — a judge that cannot be made to fail is unfalsifiable. The
    mutant ``controls/NNN.cert`` is judged against ``vectors/
    NNN.program``: mutants are paired with their anvils, because a
    wrong certificate for one program may be a right one for another."""
    base = os.path.join(lang_dir, "evidence", schema)
    lang = {"_dir": lang_dir}
    vectors = _items(base, "vectors", "program")
    if not vectors:
        raise AdmissionError(f"{base}: no evidence vectors — nothing "
                             "checked")
    for prog in vectors:
        cert_file = prog[:-len(".program")] + ".cert"
        payload = json.load(open(cert_file, encoding="utf-8"))
        if discharge(lang, prog, {"schema": schema, "payload": payload},
                     wall_s=wall_s) is None:
            raise AdmissionError(f"{base}: {os.path.basename(cert_file)} "
                                 "did not discharge")
    mutants = _items(base, "controls", "cert")
    if not mutants:
        raise AdmissionError(f"{base}: no mutant certificates — an "
                             "uncheckable judge is unfalsifiable")
    for cm in mutants:
        anvil = os.path.join(base, "vectors",
                             os.path.basename(cm)[:-len(".cert")]
                             + ".program")
        if not os.path.isfile(anvil):
            raise AdmissionError(f"{cm}: no matching vectors/"
                                 f"{os.path.basename(anvil)} to judge "
                                 "against")
        payload = json.load(open(cm, encoding="utf-8"))
        if discharge(lang, anvil, {"schema": schema, "payload": payload},
                     wall_s=wall_s) is not None:
            raise AdmissionError(f"{cm} discharged — the judge cannot "
                                 "catch a wrong certificate")
    return {"vectors": len(vectors), "controls": len(mutants)}


def check_language(lang_dir: str, manifest: dict, *,
                   wall_s: float = _DEFAULT_WALL_S) -> dict:
    lang_dir = os.path.abspath(lang_dir)
    _no_accelerator(lang_dir, manifest)
    interp = _reference(lang_dir, "interp.py")
    n = _run_vectors(lang_dir, interp, wall_s)
    if n == 0:
        raise AdmissionError(f"{lang_dir}: no vectors — nothing checked")
    mutants = sorted(glob.glob(os.path.join(lang_dir, "controls",
                                            "mutant_*.py")))
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
    evidence = {"checked": "language", "vectors": n,
                "controls": len(mutants)}
    schemas = registry.schemas({"_dir": lang_dir})
    if schemas:
        evidence["evidence"] = {
            schema: _check_evidence_schema(lang_dir, schema, wall_s)
            for schema in schemas}
    return evidence


# -- pair admission: every declared channel round-trips -----------------------

def _compare(direction: str, keeps: list[str], src_obs: dict,
             carried: dict) -> str | None:
    """None if the kept observables agree under the pair's direction,
    else a message. ``over``: the target may have more behaviors;
    ``under``: the source may."""
    for k in keeps:
        s, t = src_obs.get(k), carried.get(k)
        if direction == "exact":
            ok = s == t
        elif direction == "over":
            ok = (s == t) if not isinstance(s, bool) else (t or not s)
        elif direction == "under":
            ok = (s == t) if not isinstance(s, bool) else (s or not t)
        else:
            return f"unknown direction {direction!r}"
        if not ok:
            return f"broken on {k!r}: source {s!r}, carried {t!r}"
    return None


def _carry_obs(pair_dir: str, manifest: dict, tgt_obs: dict) -> dict | str:
    """The ``obs`` channel: carry target observables back to source
    names — ``lam_obs.py`` when shipped, else the declarative ``maps``
    renaming *is* the carry-back (identity when neither). Its honesty
    is not assumed: every ``prog`` mutant must still break the square
    *through* it, so a carry-back that flattens or invents observables
    is itself caught by the two-sided controls. When both are present
    they must agree per program. Returns the carried observables, or
    an error message."""
    lam_obs = os.path.join(pair_dir, "lam_obs.py")
    maps = manifest.get("maps") or {}
    if os.path.exists(lam_obs):
        obs_path = _tmp(json.dumps(tgt_obs, sort_keys=True).encode(), ".obs")
        res, same = runner.run_twice(lam_obs, [obs_path])
        if not same:
            return f"{lam_obs}: nondeterministic or timed out"
        if not res.ok:
            return f"{lam_obs}: rc={res.rc} err={res.err[:200]!r}"
        try:
            carried = json.loads(res.out)
        except json.JSONDecodeError:
            return f"{lam_obs}: output not JSON"
        for src_name, tgt_name in maps.items():
            if carried.get(src_name) != tgt_obs.get(tgt_name):
                return (f"declared map {src_name!r}->{tgt_name!r} "
                        "disagrees with lam_obs on this program")
        return carried
    if maps:
        carried = dict(tgt_obs)
        for src_name, tgt_name in maps.items():
            carried[src_name] = tgt_obs.get(tgt_name)
        return carried
    return tgt_obs


def _square(pair_dir: str, translate: str, manifest: dict, src_lang: dict,
            tgt_lang: dict, prog: str, input_path: str,
            wall_s: float) -> str | None:
    """The ``prog`` channel's arrival check: I_s(p) =pi= Λ(I_t(T(p))),
    both interpreters run, compared on the kept observables."""
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
    carried = _carry_obs(pair_dir, manifest, tgt_obs)
    if isinstance(carried, str):
        return carried
    msg = _compare(manifest["direction"], manifest["keeps"], src_obs,
                   carried)
    return f"square {msg}" if msg else None


def _wit_trip(pair_dir: str, lam_wit: str, translate: str, manifest: dict,
              src_lang: dict, tgt_lang: dict, prog: str, wit_file: str,
              wall_s: float) -> str | None:
    """The ``wit`` channel's round-trip: a target stimulus carried back
    must reproduce the kept observables at the source — the same
    replay the kernel will run on real witnesses, exercised per corpus
    program at admission."""
    res, same = runner.run_twice(translate, [prog], wall_s=wall_s)
    if not same or not res.ok:
        return f"{translate}: failed or nondeterministic"
    tgt_prog = _tmp(res.out, ".program")
    res, same = runner.run_twice(lam_wit, [wit_file, prog], wall_s=wall_s)
    if not same:
        return f"{lam_wit}: nondeterministic or timed out"
    if not res.ok:
        return f"{lam_wit}: rc={res.rc} err={res.err[:200]!r}"
    carried_input = _tmp(res.out, ".input")
    src_obs = interpret(os.path.join(src_lang["_dir"], "interp.py"),
                        prog, carried_input, wall_s)
    tgt_obs = interpret(os.path.join(tgt_lang["_dir"], "interp.py"),
                        tgt_prog, wit_file, wall_s)
    carried = _carry_obs(pair_dir, manifest, tgt_obs)
    if isinstance(carried, str):
        return carried
    msg = _compare(manifest["direction"], manifest["keeps"], src_obs,
                   carried)
    return f"stimulus replay {msg}" if msg else None


def _cert_trip(lam_cert: str, manifest: dict, src_lang: dict,
               tgt_lang: dict, prog: str, translate: str, cert_file: str,
               wall_s: float) -> str | None:
    """The ``cert`` channel's round-trip: a certificate valid at the
    target (precondition — garbage carries nothing) is carried back
    and must re-discharge at the source, judged by the source
    language's own evidence checker."""
    cert = json.load(open(cert_file, encoding="utf-8"))
    res, same = runner.run_twice(translate, [prog], wall_s=wall_s)
    if not same or not res.ok:
        return f"{translate}: failed or nondeterministic"
    tgt_prog = _tmp(res.out, ".program")
    if discharge(tgt_lang, tgt_prog, cert, wall_s=wall_s) is None:
        return (f"{os.path.basename(cert_file)} does not discharge at the "
                "target — the corpus certificate must be valid before it "
                "can be carried")
    res, same = runner.run_twice(lam_cert, [cert_file, prog], wall_s=wall_s)
    if not same:
        return f"{lam_cert}: nondeterministic or timed out"
    if not res.ok:
        return f"{lam_cert}: rc={res.rc} err={res.err[:200]!r}"
    try:
        carried = json.loads(res.out)
    except json.JSONDecodeError:
        return f"{lam_cert}: output not JSON"
    if discharge(src_lang, prog, carried, wall_s=wall_s) is None:
        return "carried certificate does not re-discharge at the source"
    return None


def _channel_mutants(pair_dir: str, chan: str) -> list[str]:
    return sorted(glob.glob(os.path.join(pair_dir, "controls",
                                         f"{chan}_mutant_*.py")))


def check_pair(reg: dict, pair_dir: str, manifest: dict, *,
               wall_s: float = _DEFAULT_WALL_S) -> dict:
    pair_dir = os.path.abspath(pair_dir)
    src = reg["languages"][manifest["src"]]
    tgt = reg["languages"][manifest["tgt"]]
    channels = manifest["channels"]
    unknown = [c for c in channels if c not in _CHANNELS]
    if unknown:
        raise AdmissionError(f"{pair_dir}: unknown channels {unknown}")
    if "prog" not in channels:
        raise AdmissionError(f"{pair_dir}: no prog channel — a pair with "
                             "no translation is no correspondence")
    for chan, dirs in _CHANNEL_DIRECTIONS.items():
        if chan in channels and manifest["direction"] not in dirs:
            raise AdmissionError(
                f"{pair_dir}: channel {chan!r} cannot exist at direction "
                f"{manifest['direction']!r} — it crosses only {list(dirs)}")
    if "obs" in channels and not (manifest.get("maps")
                                  or os.path.isfile(os.path.join(
                                      pair_dir, "lam_obs.py"))):
        raise AdmissionError(f"{pair_dir}: obs channel declared with "
                             "neither maps nor lam_obs.py")
    corpus = _items(pair_dir, "corpus", "program")
    if not corpus:
        raise AdmissionError(f"{pair_dir}: empty corpus")
    empty = _tmp(b"{}", ".input")
    inputs = {p: (p[:-len('.program')] + ".input"
                  if os.path.exists(p[:-len('.program')] + ".input")
                  else empty) for p in corpus}
    translate = _reference(pair_dir, "T.py")
    evidence = {"checked": "pair", "corpus": len(corpus), "channels": {}}

    # prog: the square closes per corpus program, and the pair's
    # dilution — the prog channel's conversion rate — is measured on
    # the same runs and recorded, never ranked (KERNEL.md §5).
    src_bytes = tgt_bytes = 0
    for prog in corpus:
        msg = _square(pair_dir, translate, manifest, src, tgt, prog,
                      inputs[prog], wall_s)
        if msg:
            raise AdmissionError(f"{os.path.basename(prog)}: {msg}")
        src_bytes += os.path.getsize(prog)
        tgt_bytes += len(_agree_run(translate, [prog], wall_s))
    prog_mutants = _channel_mutants(pair_dir, "prog")
    if not prog_mutants:
        raise AdmissionError(f"{pair_dir}: no prog mutants — the square "
                             "was never falsified")
    for mutant in prog_mutants:
        broken = any(
            _square(pair_dir, mutant, manifest, src, tgt, prog, inputs[prog],
                    wall_s) for prog in corpus)
        if not broken:
            raise AdmissionError(f"{mutant} passed the square — "
                                 "the corpus cannot catch a defect")
    evidence["channels"]["prog"] = {"corpus": len(corpus),
                                    "controls": len(prog_mutants)}
    evidence["ledger"] = {"dilution_bytes":
                          round(tgt_bytes / src_bytes, 3)}

    # wit: stimuli replay per corpus program that supplies one
    if "wit" in channels:
        lam_wit = _reference(pair_dir, "lam_wit.py")
        trips = [(p, p[:-len(".program")] + ".wit") for p in corpus
                 if os.path.exists(p[:-len(".program")] + ".wit")]
        if not trips:
            raise AdmissionError(f"{pair_dir}: wit channel declared but "
                                 "no corpus .wit stimulus exercises it")
        for prog, wit_file in trips:
            msg = _wit_trip(pair_dir, lam_wit, translate, manifest, src,
                            tgt, prog, wit_file, wall_s)
            if msg:
                raise AdmissionError(f"{os.path.basename(wit_file)}: {msg}")
        mutants = _channel_mutants(pair_dir, "wit")
        if not mutants:
            raise AdmissionError(f"{pair_dir}: no wit mutants — the "
                                 "carry-back was never falsified")
        for mutant in mutants:
            broken = any(
                _wit_trip(pair_dir, mutant, translate, manifest, src, tgt,
                          prog, wit_file, wall_s)
                for prog, wit_file in trips)
            if not broken:
                raise AdmissionError(f"{mutant} passed the stimulus "
                                     "replay — the corpus cannot catch a "
                                     "defect")
        evidence["channels"]["wit"] = {"corpus": len(trips),
                                       "controls": len(mutants)}

    # cert: certificates re-discharge per corpus program that supplies one
    if "cert" in channels:
        lam_cert = _reference(pair_dir, "lam_cert.py")
        trips = [(p, p[:-len(".program")] + ".cert") for p in corpus
                 if os.path.exists(p[:-len(".program")] + ".cert")]
        if not trips:
            raise AdmissionError(f"{pair_dir}: cert channel declared but "
                                 "no corpus .cert certificate exercises it")
        for prog, cert_file in trips:
            msg = _cert_trip(lam_cert, manifest, src, tgt, prog, translate,
                             cert_file, wall_s)
            if msg:
                raise AdmissionError(f"{os.path.basename(cert_file)}: {msg}")
        mutants = _channel_mutants(pair_dir, "cert")
        if not mutants:
            raise AdmissionError(f"{pair_dir}: no cert mutants — the "
                                 "carry-back was never falsified")
        for mutant in mutants:
            broken = any(
                _cert_trip(mutant, manifest, src, tgt, prog, translate,
                           cert_file, wall_s)
                for prog, cert_file in trips)
            if not broken:
                raise AdmissionError(f"{mutant} re-discharged — the corpus "
                                     "cannot catch a defect")
        evidence["channels"]["cert"] = {"corpus": len(trips),
                                        "controls": len(mutants)}

    # hint: trust-inert by construction — determinism is its whole gate
    if "hint" in channels:
        hint = _reference(pair_dir, "hint.py")
        for prog in corpus:
            res, same = runner.run_twice(hint, [prog], wall_s=wall_s)
            if not same or not res.ok:
                raise AdmissionError(f"{hint}: failed or nondeterministic "
                                     f"on {os.path.basename(prog)}")
        evidence["channels"]["hint"] = {"corpus": len(corpus)}

    acc = _check_accelerator(pair_dir, manifest,
                             [[prog] for prog in corpus], wall_s)
    if acc is not None:
        evidence["accelerator"] = acc
    return evidence


# -- search admission ---------------------------------------------------------

def _solve(script: str, prog: str, q: dict, wall_s: float) -> dict:
    res, same = runner.run_twice(
        script, [prog, q["mode"], q["observable"], str(q["bound"]),
                 str(wall_s)], wall_s=wall_s * 2 + 10)
    if not same:
        raise AdmissionError(f"{script}: nondeterministic or timed out")
    return _json_out(res, script)


def _search_corpus_ok(reg: dict, search_dir: str, manifest: dict,
                      solve: str, wall_s: float
                      ) -> tuple[int, int, list[tuple[str, dict]]]:
    """A search writes evidence; the kernel judges it (KERNEL.md §3):
    every witness must replay through the language's interpreter, every
    emitted certificate must discharge through the language's own
    evidence checker, every non-partial verdict must respect its label,
    and at least one non-partial result is required — a search that
    only abstains is vacuous. Returns (corpus size, discharged, the
    values written per program)."""
    lang = reg["languages"][manifest["language"]]
    corpus = _items(search_dir, "corpus", "program")
    if not corpus:
        raise AdmissionError(f"{search_dir}: empty corpus")
    decided, discharged, values = 0, 0, []
    for prog in corpus:
        q = json.load(open(prog[:-len(".program")] + ".q", encoding="utf-8"))
        name = os.path.basename(prog)
        if q["observable"] not in manifest["targets"]:
            raise AdmissionError(f"{name}: asks {q['observable']!r}, not "
                                 f"among targets {manifest['targets']}")
        value = _solve(solve, prog, q, wall_s)
        values.append((prog, value))
        if value["kind"] == "witness":
            fired, _ = replay(lang, prog, q["observable"],
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
                if discharge(lang, prog, value["cert"],
                             wall_s=wall_s) is None:
                    raise AdmissionError(
                        f"{name}: certificate did not discharge — the "
                        "schema must be judged by the language "
                        f"{manifest['language']!r}")
                discharged += 1
            decided += 1
        elif value["kind"] != "partial":
            raise AdmissionError(f"{name}: unknown value kind "
                                 f"{value['kind']!r}")
    if decided == 0:
        raise AdmissionError(f"{search_dir}: search abstained on the whole "
                             "corpus — vacuous")
    return len(corpus), discharged, values


def _check_ledger(search_dir: str, values: list[tuple[str, dict]],
                  wall_s: float) -> int | None:
    """The ledger executable (KERNEL.md §5) is trust-inert — what it
    writes is profiling beside the path, never a grade — so, like
    ``hint.py``, determinism and well-formedness are its whole gate:
    on every corpus program it must emit the same JSON object twice."""
    ledger = os.path.join(search_dir, "ledger.py")
    if not os.path.isfile(ledger):
        return None
    for prog, value in values:
        value_path = _tmp(json.dumps(value, sort_keys=True).encode(),
                          ".value")
        res, same = runner.run_twice(ledger, [prog, value_path],
                                     wall_s=wall_s)
        if not same:
            raise AdmissionError(f"{ledger}: nondeterministic or timed out")
        out = _json_out(res, ledger)
        if not isinstance(out, dict):
            raise AdmissionError(f"{ledger}: ledger is not a JSON object")
    return len(values)


def check_search(reg: dict, search_dir: str, manifest: dict, *,
                 wall_s: float = _DEFAULT_WALL_S) -> dict:
    search_dir = os.path.abspath(search_dir)
    solve = _reference(search_dir, "solve.py")
    n, discharged, values = _search_corpus_ok(reg, search_dir, manifest,
                                              solve, wall_s)
    mutants = sorted(glob.glob(os.path.join(search_dir, "controls",
                                            "mutant_*.py")))
    if not mutants:
        raise AdmissionError(f"{search_dir}: no negative controls")
    for mutant in mutants:
        try:
            _search_corpus_ok(reg, search_dir, manifest, mutant, wall_s)
        except AdmissionError:
            continue
        raise AdmissionError(f"{mutant} passed the corpus — "
                             "the corpus cannot catch a defect")
    evidence = {"checked": "search", "corpus": n, "controls": len(mutants)}
    if discharged:
        evidence["discharged"] = discharged
    ledgered = _check_ledger(search_dir, values, wall_s)
    if ledgered is not None:
        evidence["ledger"] = ledgered
    invocations = []
    for prog in _items(search_dir, "corpus", "program"):
        q = json.load(open(prog[:-len(".program")] + ".q", encoding="utf-8"))
        invocations.append([prog, q["mode"], q["observable"],
                            str(q["bound"]), str(wall_s)])
    acc = _check_accelerator(search_dir, manifest, invocations, wall_s)
    if acc is not None:
        evidence["accelerator"] = acc
    return evidence


# -- domain admission ---------------------------------------------------------

def check_domain(dom_dir: str, manifest: dict) -> dict:
    """A domain is the ungenerable half: a root language's name and the
    anchors that corroborate its interpreter — labels, supplied
    vectors, recorded oracle testimony (KERNEL.md §6: oracles, not
    organs). Nothing executes — but the anchors must be stated, because
    a domain without ground truth could never grade past stipulated.
    The root need not be admitted yet: the domain enters with the
    benchmark, and writing the root's interpreter is the loop's first
    act (KERNEL.md §8)."""
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
    elif kind == "search":
        evidence = check_search(reg, entry_dir, manifest, wall_s=wall_s)
    elif kind == "domain":
        evidence = check_domain(entry_dir, manifest)
    else:
        raise AdmissionError(f"unknown kind {kind!r}")
    if revision is not None:
        evidence.update(revision)
    return evidence
