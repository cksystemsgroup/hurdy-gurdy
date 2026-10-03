# `riscv` instruction tables — recorded testimony (2026-10-03)

- **What**: `checks.jsonl`, one record per check. Each check runs one
  RV64IM instruction (or a short idiom: a branch, a store and a load,
  a call and its return) on fixed operands and compares the result
  with the value the RISC-V specification gives; `build.py` computes
  the expected values from the specification's text and from no
  interpreter in the registry.
- **Oracle**: `sail_riscv_sim` 0.12 on the host — the executable of
  the Sail model that is the architecture's formal specification —
  outside the seal. The same instruction lines are assembled
  bare-metal with `riscv64-unknown-elf-gcc` 13.2.0 (`-march=rv64im
  -mabi=lp64`) and report through `tohost`. As written every table
  succeeds; and for every check, the table with that one expected
  value moved by one fails with exactly that check's number. No
  dispute stands: five expectations the generator first got wrong
  (loads at an offset from a store) were the model's to catch, and
  were corrected in the generator before any vector was written.
- **Why**: fault injection (`kernel/faults`, 2026-10-03) left 38 of 100
  sampled mutants of the `riscv` interpreter unrefused.
- **Where it entered**: `registry/languages/riscv@2`, by revision, as
  vectors 014-019, one per family; a failed check halts, and bad —
  the closing `ebreak` — is reached only when every check held.
- **Not put to the oracle**: vector 020 pins the language's own
  stipulations (registers start at 0 and sp at 0x7ffffff0, the first
  datum sits at 0x10000, unwritten memory reads 0), which no processor
  shares. The frame discipline (`fence`, the input `ecall`) is this
  language's and is covered by the earlier vectors.
- **Status**: testimony (`KERNEL.md` §6). Nothing here executes in the
  kernel. Re-derive by running `build.py` on a host with the model
  and the cross-compiler.
