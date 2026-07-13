# Pair — `btor2-interval`  ·  BTOR2 → BTOR2 (interval / range abstraction)

*Status: **registered** — brief only, no implementation yet. Registered
2026-07-13 as the second inhabitant of the direction axis
([`HANDOFF.md`](../../HANDOFF.md); the first is
[`btor2-havoc`](../btor2-havoc/README.md)).*

The platform's second **directional pair** (`direction="over"`,
[`ARCHITECTURE.md`](../../ARCHITECTURE.md) §3), registered to give the
direction axis a corroborating sibling with a **genuinely different witness
embedding**. The translator replaces the `next` function of each
**caller-named** state with a free choice *inside a caller-declared range*
`[lo, hi]`: the state is fed `lo + urem(iv, hi − lo + 1)` from a fresh input
`iv_<label>`. Where `btor2-havoc` deletes all information about a state's
update, `btor2-interval` retains the one fact the player asserts — the state
stays in its range — so its universal verdicts are sharper (fewer spurious
counterexamples) at slightly higher solver cost. The two pairs bracket a
CEGAR ladder with registered rungs: full range (≡ havoc) ⊒ subrange ⊒
singleton `[c, c]` (constant pinning) ⊒ keeping `next` (exact).

Unlike havoc — which is an over-approximation *by construction*, so its lax
square can only fail on a translator defect — the interval claim is
**falsifiable by the corpus**: if a probe drives the state outside `[lo,
hi]`, no input can reproduce that value through the range decoder, and the
square along `W` fails. Square failure means *the declared interval is not
invariant* (widen it — the abstraction was unsound); a spurious
counterexample at solve time means the interval is *too loose* (tighten
it). Both failure modes are the player's refinement demands, and both are
graded, negative-controlled artifacts — not solver-internal state.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source / target language.** BTOR2 —
  [`languages/btor2`](../../languages/btor2/README.md), the shared
  interpreter serving both roles **unchanged** (see the no-`constraint`
  note below).
- **Translator `T`.** Deterministic line-level rewrite, parameterized by a
  caller-supplied interval map `{state label → (lo, hi)}` (the player's
  parameter, never a heuristic — [`ARCHITECTURE.md`](../../ARCHITECTURE.md)
  §4; the empty map is the identity). Per mapped state of width `w`, in
  ascending state-id order with fresh ids past the largest existing id:
  drop the state's `next`; add `input` `iv_<label>`; add const/arith nodes
  computing `next(s) := lo + urem(iv, hi − lo + 1)`. Special cases: the
  full range `[0, 2^w − 1]` emits `next(s) := iv` directly (havoc's exact
  rewrite; avoids resting on the `urem`-by-zero edge), and the singleton
  `[c, c]` still emits the uniform shape (`urem(iv, 1) = 0`, so
  `next(s) := c`). Constraints: `lo ≤ hi < 2^w`, and every named state
  exists — violations are `ValueError` (caller error, not coverage).
- **Source/target interpreter `I_s` = `I_t`.** The shared BTOR2 evaluator.
- **Target-to-source `Λ`.** Identity on trace rows (states and `bad`
  observables keep their names; the added nodes introduce no observables).
- **Witness embedding `W`.** Drives `iv_<label>` with the **affine decode
  inverse** `(v − lo) mod 2^w`, where `v` is the value the deleted `next`
  produces — computed from the source system alone, so a translator defect
  cannot bend the check. Then `lo + urem(v − lo, hi − lo + 1) = v` exactly
  when `v ∈ [lo, hi]`: the square along `W` *is* the interval claim. This
  is the "genuinely different" embedding: havoc's `W` copies a value
  through; this `W` carries the abstraction's arithmetic, and its
  simulation claim has falsifiable semantic content.

## Projection `π`

Per-system, the `btor2-havoc` precedent (`projection_for`): all bit-vector
state labels plus all `bad` statuses of the **source** system. Nothing
dropped — the direction, not the projection, carries the loss story.

## Direction, and the lax square

`direction: over` — the lax contract `I_s(p) ⊑_π Λ(I_t(T(p)))`, checked as
an **exact square along `W`** on the probe bindings. Verdict transfer per
[`core/direction.py`](../../gurdy/core/direction.py): `unreachable`
transfers; `reachable` replays at the source
([`SOLVERS.md`](../../SOLVERS.md) §4). Direction and the interval map's
*declared* status are protected like `π`
([`SCALING.md`](../../SCALING.md) §9): a builder must not flip `over` to
`exact`, and must not silently widen a declared interval to make a failing
square pass — a failing square is a **finding** (the interval is not
invariant), surfaced, never absorbed.

## Fidelity target + evidence

`checked` — the lax square along `W` on every probe (conjoined coverage),
recompile-and-diff for determinism, and **three** controls: the standard
two-sided negative control, the *unsound-interval* control (a probe whose
state provably leaves the declared range must fail the square), and the
CEGAR demonstration (loose interval → spurious counterexample → tightened
interval → transferred `unreachable`).

## Coverage target

Construct inventory (conjoined, honest gaps typed):
`interval.subrange` (proper `[lo, hi]`), `interval.singleton` (`[c, c]`),
`interval.full-range` (havoc-degenerate), `interval.multi-state` (two or
more mapped states) — all four required for `built`;
`interval.wraparound` (`hi < lo` as a wrapped range) and
`interval.array-state` (same shared-evaluator gap as
`havoc.array-state`) — typed `unsupported` at registration scope. No
public external suite exists for endo-abstractions; the yardstick is the
shared reachable corpus plus the pair's probes, as for `btor2-havoc`.

## Reuses / contributes

Reuses the shared BTOR2 interpreter (both roles) and the existing solver
inventory unchanged; contributes no interpreter and no solver. Endo-hops
enumerate behind `routes(..., endo=True)` — an opt-in, player-directed
reduction, like the havoc hop.

## Notes for the implementing agent

- **Do not emit `constraint` nodes.** The shared evaluator parses but does
  not enforce them; the range must live in the `next` arithmetic (`lo +
  urem(iv, hi − lo + 1)`), which the evaluator already decides. Enforcing
  constraints would be a versioned, Lane-B shared-interpreter change this
  pair is registered *not* to need.
- Fresh ids are a pure function of the source text (max id + 1, ascending
  state-id order); anything else breaks recompile-and-diff.
- The range-size constant `hi − lo + 1` is emitted at width `w`; the
  full-range special case must bypass `urem` rather than rely on the
  `urem`-by-zero convention agreeing across every engine on the hub.
- An unknown state name or `lo > hi` is a `ValueError` (caller error), not
  a coverage gap; an array-sorted state is typed `unsupported`
  (`interval.array-state`).
