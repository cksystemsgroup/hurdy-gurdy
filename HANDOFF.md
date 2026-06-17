# Handoff — discharging the Docker-gated steps

This branch (`main`) is built and green **without Docker**: a pure-Python
framework + interpreters + pairs, validated with `z3` and (where present) the
RISC-V GCC toolchain. A handful of validations need the **pinned external
engines** that only exist in the dev image ([`DOCKER.md`](./DOCKER.md)). This
file is the to-do list for a Claude CLI running **with Docker access**: wire
each pinned tool, un-skip the gated test, and record the result.

## State today

```
python -m unittest discover -s tests        # 164 tests, OK (skipped=3)
```

The 3 skips are exactly the Docker-gated checks below. Everything else
(commuting squares, coverage 96/96 + 109/109 + 63/63, branch agreement across
the direct and Sail routes, array-witness replay, C → RISC-V reproducibility,
the full C-to-SMT long path) runs here. The platform spans:

- interpreters: RISC-V (RV64IMC + ELF), BTOR2 (incl. signed div/rem + array
  witnesses), eBPF, Sail (RV64IM, Sail-derived `Expr` semantics);
- pairs: `c-riscv`, `riscv-btor2`, `riscv-sail`, `sail-btor2`, `ebpf-btor2`,
  `btor2-smtlib`; routes `c → smtlib` decide via **two** independent backends
  and must agree.

## The dev image

Pinned inventory + digest: [`DOCKER.md`](./DOCKER.md). Relevant engines:
`pono` v2.0.0 (BTOR2 model checker), `z3` 4.16.0.0, `riscv64-unknown-elf`
gcc/binutils, `cbmc` 6.4.0, `sail_riscv_sim` (sail-riscv 0.12). Cite the image
digest with any fidelity claim.

## Gated steps (each un-skips a test)

The code locates each engine by env var or PATH and otherwise raises a typed
"unavailable" (no silent pass). With all engines wired,
`python -m unittest discover -s tests` should report **0 skips**.

### 1. RISC-V interpreter ⟂ `sail_riscv_sim`
- **Validates:** the shared RISC-V interpreter against the official Sail model.
- **Wire:** `export SAIL_RISCV_SIM=/path/to/sail_riscv_sim` and
  `SAIL_RISCV_ARGS="…"` to enable per-instruction + register-write logging.
- **Run:** `gurdy riscv-diff <elf>` ·
  test `tests/test_riscv_differential.py::TestRealOracle`.
- **Verify the format:** `differential.parse_sail_log` expects lines
  `[<cyc>] [<priv>]: 0x<pc> (0x<insn>) …` plus `x<n> <- 0x<val>`. Confirm the
  pinned emulator's actual flags/format; adjust `SAIL_RISCV_ARGS` or
  `parse_sail_log` if it differs. Compare over the riscv-tests slice (step 4).
- **Done:** `differential=ok` across the slice under the executed-instruction
  projection.

### 2. Sail interpreter ⟂ `sail_riscv_sim`
- **Validates:** the Sail-derived `Expr` semantics against the real Sail model.
- **Run:** `gurdy riscv-diff --subject sail <elf>` ·
  test `tests/test_sail_differential.py::TestSailSubjectOnElf::test_sail_interp_vs_sail_riscv_sim`.
- **Done:** the Sail interpreter's executed stream aligns with the emulator's.

### 3. Native-vs-bridged BTOR2 (`pono`)
- **Validates:** a native BTOR2 verdict matches the z3-bridged one (SOLVERS §7).
- **Wire:** `export PONO=/path/to/pono` (or `BTORMC`).
- **Run:** `python -c "from gurdy.pairs.btor2_smtlib import native_vs_bridged"`
  on a corpus · test
  `tests/test_btor2_smtlib_depth.py::TestNativeCorroboration::test_native_agrees_with_bridged`.
- **Verify the invocation:** `solvers/native_btor2._command` uses
  `pono -e bmc -k <k> <file>`; confirm pono's BMC flags and that its output
  carries a `sat`/`unsat` token (`parse_verdict`). Adjust if pono differs.
- **Done:** `agree == True` for every system in the corpus.

### 4. riscv-tests / riscv-arch-test coverage slice
- **Validates:** the RISC-V interpreter against the compliance suites (the
  coverage anchor, BENCHMARKS §4).
- **Wire:** build the pinned suites with the toolchain (or vendor them as
  pinned submodules).
- **Run:** `gurdy riscv-suite <dir>` (grades each ELF via HTIF `tohost` /
  signature; the machinery is in `languages/riscv/suite.py`).
- **Done:** the RV64IMC slice is all-pass; record per-ISA pass counts and the
  image digest in the RISC-V brief.

### 5. `c-riscv`: pin by digest + the cbmc C-differential
- **Pin:** record the dev-image digest and the exact `gcc` version/flags
  (`pairs/c_riscv/translate.py::FLAGS`) in the `c-riscv` brief, and confirm
  twice-and-diff reproducibility inside the image (`gurdy` ↦ `reproduce()`).
- **cbmc differential (not yet coded):** wire `cbmc` 6.4.0 as the independent
  C-level oracle so each long-path divergence is either a documented
  C-undefined-but-RISC-V-defined case or a localized fault. This is the next
  `c-riscv` increment (a new `c_riscv` differential, analogous to the
  `sail_riscv_sim` harness).

## Not gating, but the named next increments

- DWARF line-level carry-back for `c-riscv` `L` (currently function-level via
  symbols).
- The C extension on the Sail side; auto-deriving the Sail `Expr` trees from
  the Sail model source (today they are hand-encoded to mirror it and
  z3-checked).
- `.wit` parsing for the BTOR2 interpreter; additional native engines (AVR).

## One-shot check (inside the image)

```
export SAIL_RISCV_SIM=…  SAIL_RISCV_ARGS=…  PONO=…  RISCV_GCC=…
PYTHONPATH=. python -m unittest discover -s tests     # expect 0 skips
gurdy coverage riscv-btor2          # 96/96
gurdy path-coverage riscv smtlib    # direct 96/96, via Sail 63/63
gurdy routes c smtlib               # both backend routes for the C head
```
