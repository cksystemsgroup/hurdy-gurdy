# `riscv-btor2` corpus

This directory is the §9.2 instantiation of [BENCHMARKING.md](../../../BENCHMARKING.md)
for the `riscv-btor2` pair.

## Contract

Per §9.2 the corpus must contain ≥ 30 tasks balanced across difficulty
tiers T1–T4, with ≥ 20% tagged as lowering-sensitive. Each task carries
the metadata listed in §9.2's bullet list. The corpus is **pre-registered
in a tagged commit before condition B/C runs**; the tag commit hash is
part of the benchmark's identity (§4.4).

## Current state (2026-04-29)

| | T1 | T2 | T3 | T4 | total |
|---|---:|---:|---:|---:|---:|
| **lowering-sensitive** | 10 | 0 | 0 | 0 | 10 |
| **not LS**             | 5 | 9 | 0 | 0 | 14 |
| **total**              | 15 | 9 | 0 | 0 | **24** |

6 tasks short of the §9.2 ≥ 30 minimum. T3/T4 still empty. The §4.3
lowering-sensitive floor (20%) is comfortably exceeded (42%).

Two of the T2 tasks (0020-monotonic-x5-spacer,
0021-stayzero-x10-spacer) ship with `engine="z3-spacer"` and an
expected `proved` verdict — they exercise an inductive-invariant
question that BMC engines cannot answer at all depths. The
remaining seven T2 tasks are bound-sensitive variants with
distinct shapes (ascending counters of varying lengths, descending
counter, stride-3 counter, nested loop, post-loop arithmetic).

## Empirical-verification status

Every spec.json's expected verdict has been compared against the
actual `z3-bmc` output (with the binary path absolutized, schema
matcher pass, validate_riscv_btor2_spec pass, byte-identical
recompile). **All 18 of 18 match.**

Two engine bugs that surfaced during corpus authoring were fixed in
the same branch (commit d733a5e):

- `btor2_to_z3.py` slice/sext/uext eager-eval-of-integer-args.
- `translation/library.py` missing zero-extend for LBU/LHU/LWU.

All five engines now produce real verdicts: `z3-bmc`, `bitwuzla`,
`cvc5`, `z3-spacer`, and `pono`. The three SMT BMC engines (z3-bmc,
bitwuzla, cvc5) agree verdict-for-verdict on every corpus task —
the strongest cross-engine validation pattern available.

`z3-spacer` produces the strictly-stronger `proved` verdict on the
unreachable tasks where it can find an inductive invariant (7 of 9
unreachable tasks at this writing) and `reachable` where the
counterexample is recoverable. Long-loop tasks (0008, 0014, 0015)
time out — Spacer can't discover a useful invariant for "after K
cycles x10 = N" because the trace itself IS the invariant.

Roadmap to 30 — **not yet authored**, pre-registration is blocked
until each line below is filled or explicitly cut:

- **+0 T1** — done; 15 T1 covers the §4.2 floor.
- **+0 T2** (could add 1-2 more if needed; 9 T2 already exceeds the
  ≈25% target for a 30-task corpus). The bound-sensitive family (0002/0008/0014/0015) is
  graded as one cluster; "more of the same" doesn't add T2 evidence.
- **+6 T3** (decomposition + LearnedFact): prove a callee post-
  condition, inject as LearnedFact, settle a follow-up question.
  Requires a multi-function corpus and an `included_callees` task
  shape; needs scope-doc revision before authoring starts.
- **+5 T4** (lift-interpretation): refutations whose explanation
  must identify a specific source-level cause-PC. Blocked on the
  rubric-LLM prompt template (`bench/riscv-btor2/rubric/`) landing.

## Property convention: pc-anchor

Every task's `property.expression` has the form
`and(eq(pc, const(<halt_pc>)), <register/memory predicate>)`. The
pc anchor matters because at cycle 0 every GPR is *free*
(SCHEMA.md §7), so a bare `eq(reg(N), C)` is trivially satisfiable
at the entry step regardless of program semantics — the bad would
be `reachable` for *any* C. Anchoring on the halt PC forces the
property to hold only at the actually-reached final state, which
is what the human-language question asks about.

Validated empirically on task 0001: with a bare `eq(reg(10), 106)`
property, z3-bmc reports `reachable` (witness at cycle 0 with x10
guessed = 106); with the pc-anchored form, z3-bmc reports
`unreachable` as expected.

## Layout

```
corpus/
├── README.md              # this file
├── Makefile               # `make` builds elf + pcs.json + dwarfmap for every task
├── _emit_pcs.py           # ELF → pcs.json helper used by Makefile
├── _emit_dwarfmap.py      # ELF → source.elf.dwarfmap.json helper
└── <NNNN-slug>/           # one directory per task
    ├── task.toml          # metadata (§9.2 bullet list)
    ├── spec.json          # RiscvBtor2Spec for condition B (loadable
    │                      #   via RiscvBtor2Spec.from_jsonable)
    ├── source.S           # RV64IMC assembly — the ground truth
    ├── source.elf         # built by `make`; gitignored
    ├── pcs.json           # built by `make`; gitignored. Lookup table:
    │                      #   { entry, symbols, instructions[], ebreaks[], ecalls[] }
    └── source.elf.dwarfmap.json
                           # built by `make`; gitignored. Sidecar
                           # mapping (pc → source.S:line) the pair's
                           # loader feeds to source.line_table; the
                           # lifter's per-step file/line comes from this.
```

`<NNNN>` is a zero-padded sequence number; `<slug>` is a kebab-case
human label. Numbers are not reused — a removed task leaves a gap.

## `pcs.json` — never hand-count PCs

The assembler picks RVC compressed encodings (2 bytes) for many
instructions, so a sequence of N mnemonics is **not** N · 4 bytes wide.
After `make`, every task has a `pcs.json` with the actual addresses:

```json
{
  "entry": 65536,
  "symbols": { "_start": { "start": 65536, "end": 65546 } },
  "instructions": [
    { "pc": 65536, "size": 2, "word": "0x429d" },
    { "pc": 65538, "size": 4, "word": "0x06300013" },
    ...
  ],
  "ebreaks": [ 65544 ],
  "ecalls": []
}
```

When writing `spec.json`, look up the PC you want here and paste the
integer. The "ebreaks" and "ecalls" lists are convenience pre-filters
for the most common observable anchors (post-halt state).

## task.toml schema

```toml
[task]
id = "0001-x0-write-dropped"
task_class = "register-equality"  # short tag used for §5 reporting
difficulty = "T1"                 # T1 | T2 | T3 | T4
lowering_sensitive = true
oracle_provenance = "manual-proof" # one of:
                                   #   manual-proof | two-tool-agreement |
                                   #   executable-witness | by-construction

[question]
text = """
Is the value of register x5 ever non-zero after the program executes
the `addi x0, x0, 5` instruction?
"""

[expected]
verdict = "unreachable"           # reachable | unreachable | proved | unknown
# witness_shape is required for refutable tasks (verdict = reachable).
# Skip the [witness] table entirely when expected.verdict is unreachable.

[witness]                         # only if expected.verdict = "reachable"
bad_pc = 0x10078
halted_step = 3
observable_state = { x10 = "0xFFFFFFFF80000000" }

[notes]
text = """
Free-form notes that do NOT influence grading. Used for the human
review of borderline tasks and for the run manifest.
"""
```

## Adding a task

1. Pick the next `<NNNN>` and create `<NNNN-slug>/`.
2. Write `source.S` (RV64IMC). Required directives so the pair's loader
   can find the entry function:
   ```
       .text
       .globl  _start
       .type   _start, @function
   _start:
       ...
       .size   _start, .-_start
   ```
3. Run `make <NNNN-slug>` — produces `source.elf` and `pcs.json`.
4. Write `spec.json`. `binary.path` is `"source.elf"` (relative to the
   task dir). Look up the PCs you need in `pcs.json` (don't hand-count).
5. Write `task.toml` per the schema above.
6. Verify with the pair's own validator (one-liner shown in §"Self-test"
   below). Both round-trip and `validate_riscv_btor2_spec` should be
   silent.

## Toolchain

The `Makefile` uses `riscv64-unknown-elf-as` and `riscv64-unknown-elf-ld`
(bare-metal toolchain). These ship inside the
`christophkirsch/hurdy-gurdy-bench` image (binutils 2.44 from Debian
Trixie). To build the corpus reproducibly, run `make` inside the image:

```
docker run --rm -v "$PWD":/work -w /work \
    christophkirsch/hurdy-gurdy-bench:latest \
    make -C bench/riscv-btor2/corpus
```

Locally without Docker:
- macOS:  `brew install riscv-gnu-toolchain`
- Debian: `apt-get install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf`

## Self-test

After authoring or changing a task, verify it loads and validates:

```bash
docker run --rm -v "$PWD":/work -w /work \
    christophkirsch/hurdy-gurdy-bench:latest \
    bash -c 'pip install -e . --quiet && python -c "
import json, sys
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec, validate_riscv_btor2_spec
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
tid = sys.argv[1]
base = f\"bench/riscv-btor2/corpus/{tid}\"
with open(f\"{base}/spec.json\") as f: spec = RiscvBtor2Spec.from_jsonable(json.load(f))
diags = list(validate_riscv_btor2_spec(spec, load_riscv_binary(f\"{base}/source.elf\")))
print(\"OK\" if not diags else diags)
" 0001-x0-write-dropped'
```

## Pre-registration

Per BENCHMARKING.md §4.4, the corpus must be tagged in git **before**
condition B or C runs against it. The benchmark's identity is the
commit hash of that tag. Do not edit a task in place after pre-
registration — instead, add a new task and document the supersession
in `notes.text`.
