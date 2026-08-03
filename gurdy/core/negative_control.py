"""The two-sided negative-control harness — Phase 3 of the automated-scaling
rollout (SCALING.md §12.3, §3.2).

Before a green square is trusted on a PR, prove the square *can fail* on this
pair's probes — the I19 lesson generalized. The control grades the pair twice:

- a **seeded defect** must be caught (``mutant_pass < intact_pass``): if it
  survives, either the square is no-op'd or the probes are too weak (the
  I23/I24 class) — either way the pair is not gate-worthy;
- the **intact** pair must pass on every accepted probe (``intact_pass ==
  accepted``): proof the square is not merely always-fail.

Grading injects the (grader-authored) mutant by rebinding the pair module's
``translate`` for the duration and restoring it — a pair's ``square()`` looks up
``translate`` as a module global, so the mutant flows into the exact grading
path. This runs in-process because the mutant mutates the pair's own already
merged, trusted output; isolating *untrusted contributed* code is the
``PureOracle`` seam's job (SCALING.md §3.1). A caller may pass a stronger,
semantic mutant (e.g. one of ``tools/fault_injection.py``'s op-swaps) to test
probe *adequacy* rather than mere grader liveness.

Only ``checked``-grade pairs carry a decidable square; ``predicted``-grade hops
discharge faithfulness per run and have no build-time square to control.

The third assert of §3.2 — ``grade(prior_merged_version) == PASS`` — is
``prior_version_control``: the pair as it stood at the PR's merge-base (its
``translate`` on its own inventory's probes) graded under the *current* square,
so the not-always-fail witness rests on history's known-good rather than on the
PR's own code, which is what the intact side has to use. A prior version that
cannot run in the current tree (new pair, unresolvable ref, non-additive shared
change) is a typed ``ok=None`` with a note, never a silent PASS or a spurious
FAIL — deciding such a change is the coordinator's Lane-B business.
"""

from __future__ import annotations

import importlib
import io
import subprocess
import sys
import tarfile
import tempfile
import types
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from .errors import Unsupported
from .registry import Pair

_ROOT = Path(__file__).resolve().parents[2]


def _pair_module(pair: Pair) -> Any:
    return importlib.import_module(f"gurdy.pairs.{pair.id.replace('-', '_')}")


def _accepts(translate: Callable[[Any], Any], program: Any) -> bool:
    try:
        translate(program)
        return True
    except Unsupported:
        return False


def truncate_mutant(pair: Pair) -> Callable[[Any], bytes]:
    """A gross-defect mutant guaranteed to break a checked pair's square:
    keep only the first half of the emitted artifact. Tests grader *liveness*
    (the square is running), not probe adequacy."""
    real = _pair_module(pair).translate

    def mutant(program: Any) -> bytes:
        art = bytes(real(program))
        return art[: max(1, len(art) // 2)]

    return mutant


def grade(pair: Pair, translate_override: Callable[[Any], Any] | None = None,
          *, probes: dict[str, Any] | None = None,
          scope: Callable[[Any], bool] | None = None) -> int:
    """Count in-scope probes whose square passes, optionally with the pair's
    ``translate`` rebound to ``translate_override`` (restored afterward).
    ``probes`` defaults to the pair's registered inventory; ``scope`` (which
    probes count) defaults to acceptance by the *real* translator, so a
    mutation cannot silently shrink it. The prior-version control passes the
    prior version's own probes and acceptance instead — the scope of history's
    known-good claim, not of the PR's code (§3.2)."""
    mod = _pair_module(pair)
    real = mod.translate
    if probes is None:
        probes = pair.probes
    if scope is None:
        scope = lambda program: _accepts(real, program)  # noqa: E731
    if translate_override is not None:
        mod.translate = translate_override
    passed = 0
    try:
        for program in probes.values():
            if not scope(program):
                continue
            try:
                result = pair.square(program)
            except Exception:                 # a crash in the square = caught
                continue
            if getattr(result, "ok", False):
                passed += 1
    finally:
        mod.translate = real
    return passed


@dataclass
class ControlResult:
    pair: str
    accepted: int
    intact_pass: int
    mutant_pass: int
    caught: bool                              # the seeded defect was caught
    intact_ok: bool                           # every accepted probe passes intact
    ok: bool                                  # the two-sided control holds


def two_sided_control(pair: Pair,
                      mutant: Callable[[Any], Any] | None = None) -> ControlResult | None:
    """Run the two-sided control on a checked-grade pair. Returns ``None`` for a
    pair with no decidable square (nothing to control at build time)."""
    if pair.square is None or not pair.probes:
        return None
    real = _pair_module(pair).translate
    accepted = sum(1 for p in pair.probes.values() if _accepts(real, p))
    intact = grade(pair)
    mut = mutant if mutant is not None else truncate_mutant(pair)
    mutant_pass = grade(pair, translate_override=mut)
    caught = mutant_pass < intact
    intact_ok = intact == accepted
    return ControlResult(pair.id, accepted, intact, mutant_pass,
                         caught, intact_ok, caught and intact_ok)


# --- the prior-merged-version side (§3.2, third assert) ----------------------

@dataclass
class PriorVersionResult:
    pair: str
    base: str                                 # ref the prior version was read at
    accepted: int                             # prior probes its translate accepts
    passed: int                               # of those, passing the current square
    ok: bool | None                           # None: could not run — see note
    note: str | None = None


def _git_archive(ref: str, path: str) -> bytes | None:
    """The prior source, straight from the object store — the working tree
    (and anything a PR did to it) never enters. ``None`` if the ref is
    unresolvable or the path did not exist there."""
    try:
        out = subprocess.run(["git", "archive", ref, "--", path], cwd=_ROOT,
                             capture_output=True, check=True)
        return out.stdout
    except Exception:
        return None


@contextmanager
def _prior_pair(pkg_dir: Path, mod_dir: str) -> Iterator[tuple[Callable[[Any], Any], dict[str, Any]]]:
    """Import a prior pair version's ``translate`` and ``ALL_PROBES`` from an
    extracted source tree under a synthetic package name. The package
    ``__init__`` is deliberately never executed — it would re-register the
    pair's id, a hard registry error — and the synthetic modules are dropped
    on exit, so nothing later resolves to the prior version by accident.
    Parent-relative imports (``...core``, ``...languages``) resolve to the
    *current* shared layer: exactly the tree the prior pair must still pass
    under."""
    synth = f"gurdy.pairs._prior_{mod_dir}"
    parent = types.ModuleType(synth)
    parent.__path__ = [str(pkg_dir)]
    parent.__package__ = synth
    sys.modules[synth] = parent
    try:
        translate = importlib.import_module(f"{synth}.translate").translate
        probes = importlib.import_module(f"{synth}.inventory").ALL_PROBES
        yield translate, probes
    finally:
        for name in [n for n in sys.modules
                     if n == synth or n.startswith(synth + ".")]:
            del sys.modules[name]


def prior_version_control(pair: Pair, base_ref: str) -> PriorVersionResult | None:
    """The §3.2 base-version side: ``grade(prior_merged_version) == PASS``.

    Grades the pair as it stood at ``base_ref`` — its ``translate``, scoped to
    the probes of its own inventory it accepts — under the current square,
    lift, and shared layer. For a widening PR the prior ``partial``/``built``
    version is a perfect known-good, so a miss means the PR's harness would
    have failed history: the square was redefined, not extended. Probes the PR
    added are outside the prior claim and outside this control's scope; the
    intact and mutant sides own them.

    Returns ``None`` for a pair with no decidable square (nothing to control
    at build time, mirroring ``two_sided_control``). ``ok=None`` with a note
    when the control cannot run: the pair is new at ``base_ref``, the ref is
    unresolvable, the prior source will not load or grade in the current tree
    (a non-additive shared change — Lane B's business, not a FAIL here), or
    the prior version accepts none of its probes (no known-good evidence)."""
    if pair.square is None or not pair.probes:
        return None
    mod_dir = pair.id.replace("-", "_")
    rel = f"gurdy/pairs/{mod_dir}"
    tar_bytes = _git_archive(base_ref, rel)
    if tar_bytes is None:
        return PriorVersionResult(
            pair.id, base_ref, 0, 0, None,
            f"no prior version at {base_ref} (new pair, or unresolvable ref)")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
                tf.extractall(tmp, filter="data")
            with _prior_pair(Path(tmp) / rel, mod_dir) as (prior_t, prior_probes):
                accepted = sum(1 for p in prior_probes.values()
                               if _accepts(prior_t, p))
                if accepted == 0:
                    return PriorVersionResult(
                        pair.id, base_ref, 0, 0, None,
                        "prior version accepts none of its own probes — "
                        "no known-good evidence")
                passed = grade(pair, translate_override=prior_t,
                               probes=prior_probes,
                               scope=lambda p: _accepts(prior_t, p))
        except Exception as exc:              # prior code meeting today's tree
            note = (f"prior version failed to load or grade: "
                    f"{type(exc).__name__}: {exc}")
            return PriorVersionResult(pair.id, base_ref, 0, 0, None,
                                      note.replace(tmp, "<tmp>"))
    return PriorVersionResult(pair.id, base_ref, accepted, passed,
                              passed == accepted)
