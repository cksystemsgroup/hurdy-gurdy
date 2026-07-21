# Pair — `btor2-havoc`  ·  BTOR2 → BTOR2 (localization abstraction)

*Status: **partial** — built (`gurdy/pairs/btor2_havoc/`, tests in
`tests/test_btor2_havoc_pair.py`): the rewrite, the witness embedding, the
lax square along it, conjoined construct coverage 7/8 (the honest gap is
`havoc.array-state` — no array-valued inputs in the shared interpreter), the
two-sided negative control, and the CEGAR demonstration (spurious
counterexample → refinement → transferred universal verdict).*

The platform's first **directional pair** (`direction="over"`,
[`ARCHITECTURE.md`](../../ARCHITECTURE.md) §3) and its first **endo-pair**
(source language = target language, [`POTENTIAL.md`](../../POTENTIAL.md) §4).
The translator deletes the `next` functions of **caller-named** states and
feeds each such state from a fresh input (`havoc_<label>`) instead — the
classic localization abstraction: a smaller-constraint system whose behaviors
are a *superset* of the source's. The point is cost: a question decided on
the abstraction is cheaper, and when the verdict is `unreachable` it
**transfers** to the source on the strength of the direction alone. A
`reachable` on the abstraction proves nothing until its witness replays at
the source; a replay failure is a **spurious counterexample** — the player's
refinement demand (havoc fewer states). That loop is
counterexample-guided abstraction refinement with the refinements as
registered, audited artifacts.

Because this is an endo-pair, it multiplies the question space of everything
upstream: any route that reaches BTOR2 can take the abstraction hop before
the bridge (`... → btor2-havoc → btor2-smtlib`). Endo-hops enumerate behind
`routes(..., endo=True)` — an abstraction is a player-directed reduction (the
havoc set is the player's parameter), never a silently-chosen one.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source language.** BTOR2 —
  [`languages/btor2`](../../languages/btor2/README.md).
- **Target language.** BTOR2 — the same registered language; the shared
  interpreter serves both roles unchanged.
- **Translator `T`.** The deterministic line-level rewrite: drop the `next`
  of each havocked state, append `input` + `next` lines with fresh ids past
  the largest existing id, in ascending state-id order. The havoc set is a
  **parameter the caller supplies** (never a heuristic —
  [`ARCHITECTURE.md`](../../ARCHITECTURE.md) §4); the empty set is the
  identity. `init` lines and every untouched line pass through verbatim.
- **Source/target interpreter `I_s` = `I_t`.** The shared BTOR2 evaluator.
- **Target-to-source `Λ`.** The identity on trace rows: states and `bad`
  observables are untouched by the rewrite, so a target behavior already
  speaks the source vocabulary.
- **Witness embedding `W`** (directional pairs only,
  [`PAIRING.md`](../../PAIRING.md) §1): maps a source binding to the target
  binding that drives each `havoc_*` input with exactly the value the deleted
  `next` function produces — the executable form of the simulation claim.
  Computed from the source system alone, so a translator defect cannot bend
  the check.

## Projection `π`

Per-system (the `crn-smtlib` / `sail-btor2` dynamic-projection precedent):
all bit-vector state labels plus all `bad` statuses of the **source** system
(`projection_for`). Nothing is dropped — the direction, not the projection,
is where this pair's honesty about loss lives: the abstraction *adds*
behaviors rather than discarding observables.

## Direction, and the lax square

The square is the **lax** contract `I_s(p) ⊑_π Λ(I_t(T(p)))` — every source
behavior has a target counterpart on `π`. It is checked as an **exact square
along `W`**: `align(I_s(p, b), Λ(I_t(T(p), W(b))), π)` for the probe
bindings, so the oracle, conjoined coverage, determinism ratchet, and
negative controls apply unchanged. Verdict transfer is the asymmetry of
[`core/direction.py`](../../gurdy/core/direction.py): `unreachable` transfers
along `over`; `reachable` never rests on transfer (it replays at the source —
[`SOLVERS.md`](../../SOLVERS.md) §4 — which is also what exposes a spurious
abstraction counterexample).

## Fidelity target + evidence

`checked` — the lax square runs on every probe (conjoined 7/8), the
two-sided negative control proves the check can fail, and
`recompile-and-diff` proves determinism. The direction is a **protected
declaration** like `π` ([`SCALING.md`](../../SCALING.md) §9): a builder must
not flip `over` to `exact`.

## Soundness story

- A **false `unreachable`** on the abstraction would need the abstraction to
  miss a source behavior — exactly what the lax square along `W` checks on
  the corpus, construct by construct.
- A **false `reachable`** is impossible to launder: the witness is carried
  back and replayed through the shared source interpreter, which is not this
  pair's to author (the universal-only attack surface,
  [`SCALING.md`](../../SCALING.md) §2, unchanged by direction).
- The identity `Λ` and the append-only rewrite keep the observable
  vocabulary byte-identical, so a divergence localizes to a step and a state
  label like any exact pair's.

## Standing demand — the campaign's citation (promoted 2026-07-21)

Board entry **`9c26710bf77f`** (kind `reduction`, in-set), derived from
the `hwmcc-sosylab-beem` campaign books
(`paper/frontier/results/hwmcc-sosylab-beem/books.jsonl`, iteration 0):
**31 distinct `btor2` reachability questions**, origin `campaign`,
budgets `{resource-out: 31}` — btormc spent the declared 300 s wall at
k=20 on each. Required contract joined over the citing questions: no
named observables, no assurance floor — the demand is pure **cost**.
The brief regenerates verbatim from the books
(`gurdy frontier-promote 9c26710bf77f --ledger …/books.jsonl`); this
section is its registration, per AGENTS.md §1.

**Take-up.** [`tools/havoc_player.py`](../../tools/havoc_player.py)
(`frontier_loop.py --engine havoc`) plays this pair against the
standing demand exactly as prescribed above: advisor-named free havoc
set plus the farthest half of the refinement ladder
(`gurdy suggest-reduction`), CEGAR on spurious counterexamples
(declared budget: 4 rounds, cited in the iteration's caps),
`unreachable` transferring on the `over` direction, `reachable` only
after source replay. A question the reduction still cannot close
re-books its cost demand — spent evidence for the next target, not a
hidden failure.

## Notes for the implementing agent

- Array-sorted states are typed `Unsupported` (`havoc.array-state`): the
  shared evaluator has no array-valued inputs. Widening this means extending
  the shared interpreter first — a versioned, Lane-B shared change.
- An unknown state name is a `ValueError` (caller error), not a coverage gap.
- The fresh-input ids are a pure function of the source text (max id + 1,
  ascending state order); anything else breaks recompile-and-diff.
- The havoc set need not be guessed: the reduction advisor
  (`gurdy suggest-reduction`, 2026-07-14) names the **free** states
  (outside the question's cone of influence — zero precision loss,
  negative-controlled) and orders the cone states farthest-first as the
  CEGAR ladder. Advisory only; the set stays the player's parameter.
