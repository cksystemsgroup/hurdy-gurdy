# Benchmarks — pinned suites

Pinned benchmark JSONs (`core/benchmark.py` schema: suite, source
snapshot, per-instance sha256 + question + optional expected label),
authored by [`tools/pin_family.py`](../tools/pin_family.py) and
consumed by `gurdy saturation` and
[`tools/frontier_loop.py`](../tools/frontier_loop.py). A file here is
a pin, not a result: fetch is streamed-with-pin at run time
([`BENCHMARKS.md`](../BENCHMARKS.md) §4), one instance at a time,
hash-verified against these entries.

| Suite | Families | Instances | Labels |
|---|---|---|---|
| [`hwmcc-sosylab-beem.json`](./hwmcc-sosylab-beem.json) | `bv/2024/sosylab`, `bv/2019/beem` | 110 | 5, inherited from the hand-pinned slice (`tools/abstraction_bench.py`) |

`hwmcc-sosylab-beem` is the first widening of the pre-registered HWMCC
protocol ([`FRONTIER.md`](../FRONTIER.md) §5; the frontier paper's
§6.3): same mirror, same commit as the six-instance slice, widened to
the two labeled-adjacent bit-vector families. Unlabeled instances get
their ground truth the protocol's way — engine agreement plus witness
replay — never by assumption; external labels (e.g. harvested
competition results) enter through `pin_family.py --labels`, which
refuses contradictions with standing pins.
