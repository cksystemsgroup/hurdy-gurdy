# Language — C

The C programming language: the **source** end of the platform's
highest-altitude pair, `c-riscv`.

## Formal semantics (source of truth)

The C abstract machine as defined by the ISO C standard. The meaning of a
C program is the observable behavior of the abstract machine, **including
the boundary of undefined behavior** — signed overflow, division by zero,
out-of-bounds access, and the rest. That boundary is the whole point of
pairing C with a concrete ISA: behavior the C standard leaves undefined is
*defined* once the program is lowered to RISC-V, and a question asked about
the lowered program can have a definite answer where a question asked about
the C abstract machine cannot.

A pair brief that needs a narrower object (a specific C subset, a fixed set
of compiler flags, a target data model) states it; the language itself is
the ISO abstract machine.

## Shared interpreter

**Role: source.** C is, today, only ever a source language (its only
registered pair is `c-riscv`).

The `c-riscv` brief deliberately does **not** require a full C interpreter
to validate its square: an opaque, pinned compiler's faithfulness is
established *downstream* on the lowered RISC-V program, not by mirroring C
execution ([`pairs/c-riscv`](../../pairs/c-riscv/README.md),
[`PAIRING.md`](../../PAIRING.md) §6). So a shared C interpreter is **not
yet required** and is not part of the initial build.

If a future pair needs one (for example, to lift `c-riscv` from
`reproducible` toward `checked`/`proved` by executing the C abstract
machine directly), it is built here, against the ISO semantics, following
the [`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5 conventions, and shared
from this language.

## Pairs over this language

- [`c-riscv`](../../pairs/c-riscv/README.md) — source.
