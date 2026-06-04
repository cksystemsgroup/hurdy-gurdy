# SOTA baselines for the riscv-btor2 Pareto comparison

> Design doc for P3 of `../../../PLAN.md`. Defines the per-tool
> subprocess wrapper interface, the uniform output schema, and the
> deferral status of each candidate tool.
>
> **No code in this iteration.** This file is the spec a future
> iteration uses to land each adapter (`P3.2 → P3.6`).

## What this directory is for

Hurdy-gurdy's "outperform SOTA" claim (`V2_BOOTSTRAP.md` §5) is
operationally a **Pareto-table comparison** against established
C/C++ verification tools on the same corpus. This directory will
hold one adapter per tool plus a thin aggregator. The adapters
share:

- a uniform output schema (Section 2),
- a uniform invocation interface (Section 3),
- a uniform deferral story for macOS (Section 4).

Hurdy-gurdy itself participates in this comparison as one row of
the Pareto table, using `framework_oracle.py`'s lifted verdict and
`oracle_align.py`'s alignment status as its own per-task signal.

## 1. The candidate tools

| Tool             | Input              | Verdict surface             | Why it's a peer            | Adapter priority |
|------------------|--------------------|-----------------------------|----------------------------|------------------|
| **CBMC**         | C / C++ source     | `VERIFICATION FAILED`/`SUCCESSFUL` + counterexample | Long-standing C BMC reference; strong on pointer arithmetic; brew-installable on macOS. | **P3.2 — first.** |
| **ESBMC**        | C / C++ source     | similar to CBMC (`VERIFICATION FAILED`/`SUCCESSFUL`/`UNKNOWN`) | Second-vendor C BMC. Stronger on floats (out of scope here) and concurrency (out of scope). | **P3.3.** |
| **SeaHorn**      | LLVM bitcode (`.bc`) | `unsat`/`sat`/`unknown` from internal Horn engine | Strong on inductive loop invariants — the kind of program where hurdy-gurdy's z3-spacer / pono-ind path competes. | **P3.4 (Docker only).** |
| **Symbiotic**    | LLVM bitcode (`.bc`) | `RESULT: true`/`RESULT: false (...)` | Symbolic execution + slicing pipeline; "best-of-all-engines" style. Strong reach baseline. | **P3.5 (Docker only).** |
| **Pono-native**  | BTOR2               | `sat`/`unsat`/`unknown`     | The only peer that consumes the *same* artifact hurdy-gurdy emits — apples-to-apples on the BTOR2 pipeline (isolates translation quality from solver quality). | **P3.6.** |
| **KLEE** (deferred) | LLVM bitcode    | Symbolic execution traces   | Bug-finder, not strictly a verifier. **Excluded from P3** — different question class. May add later as "no-false-positive" comparator. | Excluded. |
| **CPAchecker** (deferred) | C source  | SV-COMP-style YAML verdict  | Strong SV-COMP champion but very heavy install + Java toolchain. **Deferred until P3 has settled on Linux/Docker workflow.** | Deferred. |

Five adapters land on the table in P3. Two more (KLEE, CPAchecker)
have explicit deferral rationales so they don't keep coming up
mid-iteration.

## 2. Uniform output schema

Every adapter emits one JSON line per `(task, question)` cell on
stdout. Fields:

| Field         | Type         | Notes                                                                                |
|---------------|--------------|--------------------------------------------------------------------------------------|
| `tool`        | string       | `cbmc`, `esbmc`, `seahorn`, `symbiotic`, `pono-native`, `hurdy-gurdy`.                |
| `task`        | string       | Task id (`0007-simple-add-baseline`), or `task::qN` for multi-question tasks.        |
| `verdict`     | string       | One of `reachable` / `unreachable` / `proved` / `unknown` / `error` / `timeout`.    |
| `wall_s`      | float        | Wall clock for the per-task subprocess, capped by `--timeout`.                       |
| `rss_mb`      | float        | Peak resident-set MB (from `getrusage`); 0 if the OS doesn't report.                 |
| `expected`    | string       | The task's pre-registered `expected.verdict` (copied from `task.toml`).              |
| `correct`     | bool \| null | `verdict == expected` when both are non-`unknown`/`timeout`/`error`; else `null`.     |
| `cmd`         | string       | The literal command the adapter ran (for audit / re-run).                            |
| `raw_excerpt` | string       | First 4 KiB of stdout+stderr (for audit). Adapter may truncate.                     |
| `notes`       | string       | Free-text adapter notes (e.g. "engine selected: z3-bmc").                            |

The schema is intentionally identical to the hurdy-gurdy
self-row, so the aggregator just concatenates JSONL streams.

## 3. Adapter interface

Each adapter is one Python file at
`bench/riscv-btor2/baselines/<tool>.py`. Required surface:

```python
def run_one(
    task_dir: Path,
    *,
    timeout_s: int = 60,         # per-task wall-clock cap (RAM safety)
    memory_mb: int = 2000,       # per-process RSS cap (RAM safety)
) -> dict:
    """Run <tool> on this task; return one row of the schema in §2.

    Raises only on adapter-side bugs (missing binary, malformed
    output). Tool-side `unknown` / `timeout` / `error` verdicts
    are normal returns, not exceptions.
    """
```

A thin `__main__` block lets each adapter be run standalone for
quick smoke checks:

```python
if __name__ == "__main__":
    # argparse: --task <id>, --corpus <path>, --timeout, --memory.
    # Emit one JSON line per matched task. Exit 0; never 1.
```

The aggregator (`engine_bench.py` — already exists; will be
extended in P3.7) reads each adapter's JSONL output and produces
the Pareto table.

## 4. Deferral story — macOS reality

The development machine for this branch is macOS. **All five
candidate tools have macOS issues of varying severity:**

| Tool          | macOS path                                         | Decision |
|---------------|----------------------------------------------------|----------|
| CBMC          | `brew install cbmc` works; single binary.          | **Native.** |
| ESBMC         | macOS binary releases exist but trail Linux; some Z3 dep issues. | **Native if `brew install esbmc` works on a smoke test; else Docker.** |
| SeaHorn       | Linux-only realistically (LLVM toolchain pinned).   | **Docker.** Image: `seahorn/seahorn-llvm10:nightly` (verify in P3.4). |
| Symbiotic     | Linux-only realistically.                          | **Docker.** Image: `staticafi/symbiotic` (verify in P3.5). |
| Pono-native   | Builds from source on macOS; cross-platform.       | **Native (compile from source) or Docker.** |

Per `V2_AGENT_LOOP.md` §4 the agent **cannot** autonomously
`docker pull` or install system packages. So:

- **P3.2 (CBMC)** is autonomous-safe **if** the user has `cbmc`
  already on PATH. The adapter must detect absence and skip
  gracefully (`verdict=error`, `notes="cbmc not found on PATH"`).
- **P3.3–P3.6** require the user to opt in: either install
  natively, or set `HURDY_DOCKER_BASELINES=1` and have the right
  Docker images pulled. Adapters that need Docker check for
  `docker` on PATH and skip-with-note if absent.

A future iteration may add `bench/riscv-btor2/baselines/
docker-compose.yml` to standardize the Docker invocation, but
that is **out of scope for P3.2** and requires user authorization.

## 5. C-source availability across the corpus

The Pareto comparison only makes sense for tasks where:

- hurdy-gurdy has an ELF (always — `source.elf`),
- and SOTA tools have a peer input (C source for CBMC/ESBMC;
  LLVM bitcode for SeaHorn/Symbiotic; BTOR2 for Pono-native).

A scan of the existing corpus (P3.1 audit task) must:

- list tasks that ship a `source.c` alongside `source.elf` —
  these participate fully.
- list tasks that ship only ELF (hand-written assembly seeds) —
  these participate only against Pono-native.

The aggregator (P3.7) records "tool was not applicable to this
task" as `verdict=skip`, not `error`. Pareto math excludes skip
rows from per-task pairs.

## 6. Timeline (rough)

These slot into PLAN.md P3.* (no fixed dates):

- **P3.1** — audit existing corpus for C-source availability;
  write a `corpus_inputs.json` enumerating per-task input formats.
- **P3.2** — CBMC adapter + brew-install smoke.
- **P3.3** — ESBMC adapter (native or Docker fallback).
- **P3.4** — SeaHorn adapter (Docker).
- **P3.5** — Symbiotic adapter (Docker).
- **P3.6** — Pono-native adapter (most apples-to-apples).
- **P3.7** — aggregator extension in `engine_bench.py`; first
  Pareto snapshot in `V2_PROGRESS.md`.

## 7. Open questions deferred until evidence

- Whether to also include verifier-portfolios (CPAchecker,
  Ultimate Automizer) — heavy installs; only after P3.2–P3.6
  settle.
- Whether hurdy-gurdy's multi-engine cross-oracle
  (`oracle_cross.py`) should compress into a single Pareto row
  ("best of all engines") or stay as one row per engine. Default
  the question to "one row per engine" until the table is read.
- Whether to publish raw per-tool outputs in the repo. Defer until
  the size cost is concrete (likely tens of MB per slice; consider
  `bench/riscv-btor2/baselines/_runs/` as gitignored).
