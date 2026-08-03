# Benchmarks — pinned suites

Pinned benchmark JSONs (`core/benchmark.py` schema: suite, source
snapshot, per-instance sha256 + question + optional expected label),
authored by [`tools/pin_family.py`](../tools/pin_family.py) (HWMCC)
and [`tools/pin_svcomp.py`](../tools/pin_svcomp.py) (SV-COMP) and
consumed by `gurdy saturation` and
[`tools/frontier_loop.py`](../tools/frontier_loop.py). A file here is
a pin, not a result: fetch is streamed-with-pin at run time
([`BENCHMARKS.md`](../BENCHMARKS.md) §4), one instance at a time,
hash-verified against these entries.

| Suite | Families | Instances | Labels |
|---|---|---|---|
| [`hwmcc-sosylab-beem.json`](./hwmcc-sosylab-beem.json) | `bv/2024/sosylab`, `bv/2019/beem` | 110 | 5, inherited from the hand-pinned slice (`tools/abstraction_bench.py`) |
| [`svcomp-bitvector.json`](./svcomp-bitvector.json) | `c/bitvector` | 36 | 36, from the task definitions' own `expected_verdict` |

`hwmcc-sosylab-beem` is the first widening of the pre-registered HWMCC
protocol ([`FRONTIER.md`](../FRONTIER.md) §5; the frontier paper's
§6.3): same mirror, same commit as the six-instance slice, widened to
the two labeled-adjacent bit-vector families. Unlabeled instances get
their ground truth the protocol's way — engine agreement plus witness
replay — never by assumption; external labels (e.g. harvested
competition results) enter through `pin_family.py --labels`, which
refuses contradictions with standing pins.

`svcomp-bitvector` opens the second benchmark act (FRONTIER.md §5:
source-level C questions down the full spine): the `c/bitvector`
family of the sv-benchmarks upstream at the `svcomp25` release tag,
pinned by commit over the `gitlab:` source (the GitHub mirror is
archived at svcomp21). Each instance pins the *program* bytes; the
task definition that supplied its `unreach-call` verdict rides in
`meta` with its own sha256, so the label's provenance is pinned too.
Of the family's 70 tasks, 34 are typed skips
(`no-unreach-call-property` — termination/overflow-only questions),
reported by the authoring run, never silently dropped.

## Scoping the c-riscv path against `svcomp-bitvector`

[`tools/scope_svcomp.py`](../tools/scope_svcomp.py) walks every
pinned instance through the *actual* front of the spine — pinned
fetch → the pair's pinned compiler + flags → a freestanding link
against a scoping shim → the riscv-btor2 hub translator — and types
what stops it ([`svcomp-bitvector.scope.json`](./svcomp-bitvector.scope.json)
is the committed report; per-toolchain, its toolchain line recorded).
The census of 2026-07-26:

* **The mechanical path is 100% green**: 36/36 fetch, compile at
  rv64im/lp64, link with an *empty* residual libc surface (the shim's
  nondet stubs + `__assert_fail`/`abort`/`exit` suffice — the family
  demands nothing else), and reach the BTOR2 hub (389–4968 lines, no
  `Unsupported` instruction anywhere).
* **0/36 answerable today**, typed: `harness.property` ×36
  (`unreach-call` is pc-reachability of an anchor symbol;
  `pairs/riscv-btor2` emits only a `reg_eq` bad signal),
  `harness.nondet` ×36 (every task reads `__VERIFIER_nondet_*`; the
  hub model is deterministic in `(image, init_regs)` — free-input
  modeling is a pair-level design decision, not a stub),
  `pin.data-model` ×10 (ILP32-labeled tasks using plain `long` under
  the lp64 pin; an under-approximating proxy, stated as such).
* **All 36 linked ELFs carry all three pc anchors**
  (`reach_error`, `__assert_fail`, `abort`). The sound anchor is the
  shim's `__assert_fail`/`abort`: they live in their own translation
  unit and the pinned flags have no LTO, so calls into them cannot be
  inlined away — task-defined `reach_error` alone can be (`-O2`).

Implementation order the census fixes: (1) a pc-anchor reachability
property in riscv-btor2 (the `reg_eq` mechanism's sibling), (2)
nondet-as-free-input modeling, (3) the ILP32 story for the 10
divergent tasks (pin migration or an int-only slice), with the
harness/shim as a versioned artifact. Nondet width demand measured:
int-width types dominate (`uint` ×28, `int` ×12, `char` ×10); plain
`long` appears only in `gcd_4` + the `s3_*` family.
