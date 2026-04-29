# `riscv-btor2` corpus

This directory is the §9.2 instantiation of [BENCHMARKING.md](../../../BENCHMARKING.md)
for the `riscv-btor2` pair.

## Contract

Per §9.2 the corpus must contain ≥ 30 tasks balanced across difficulty
tiers T1–T4, with ≥ 20% tagged as lowering-sensitive. Each task carries
the metadata listed in §9.2's bullet list. The corpus is **pre-registered
in a tagged commit before condition B/C runs**; the tag commit hash is
part of the benchmark's identity (§4.4).

## Layout

```
corpus/
├── README.md              # this file
├── Makefile               # builds source.elf from source.S for every task
└── <NNNN-slug>/           # one directory per task
    ├── task.toml          # metadata (§9.2 bullet list)
    ├── spec.json          # RiscvBtor2Spec for condition B (loadable
    │                      #   via RiscvBtor2Spec.from_jsonable)
    ├── source.S           # RV64IMC assembly — the ground truth
    └── source.elf         # built by `make`; gitignored
```

`<NNNN>` is a zero-padded sequence number; `<slug>` is a kebab-case
human label. Numbers are not reused — a removed task leaves a gap.

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
2. Write `source.S` (RV64IMC; see existing tasks for the conventions).
3. Write `spec.json` (RiscvBtor2Spec; the `binary.path` is relative to
   the task directory: `"source.elf"`).
4. Write `task.toml` per the schema above.
5. Run `make <NNNN-slug>` to build `source.elf` (requires the RISC-V
   toolchain — see "Toolchain" below).
6. Verify the spec round-trips through `RiscvBtor2Spec.from_jsonable`.

## Toolchain

The `Makefile` uses `riscv64-unknown-elf-as` and `riscv64-unknown-elf-ld`
(bare-metal toolchain). The `christophkirsch/hurdy-gurdy-bench` image
does not ship these yet — a follow-up Dockerfile change will add
`gcc-riscv64-unknown-elf` and `binutils-riscv64-unknown-elf`. Pin the
toolchain version in the same image so source.elf bytes are reproducible.

Until then, build locally with whatever bare-metal RISC-V toolchain is
on your system (Homebrew: `riscv-gnu-toolchain`).

## Pre-registration

Per BENCHMARKING.md §4.4, the corpus must be tagged in git **before**
condition B or C runs against it. The benchmark's identity is the
commit hash of that tag. Do not edit a task in place after pre-
registration — instead, add a new task and document the supersession
in `notes.text`.
