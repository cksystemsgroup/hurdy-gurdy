# Registry — languages, interpreters, pairs, and paths

The live state of the platform: which languages are registered (and own
the shared interpreters), which pairs exist, and which paths they induce.
A pair or language is *registered* when its brief exists here and under
[`languages/`](./languages/) or [`pairs/`](./pairs/); it is *built* when an
agent has delivered it to the [`PAIRING.md`](./PAIRING.md) contract.

## Languages

Each language carries a formal semantics and owns the source/target
interpreter shared by every pair that touches it
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §6). Briefs:
[`languages/`](./languages/).

| Language  | Brief | Formal semantics (source of truth) | Interpreter shared by |
|-----------|-------|------------------------------------|-----------------------|
| C         | [`languages/c`](./languages/c/README.md)         | the C abstract machine (ISO C) | `c-riscv` |
| RISC-V    | [`languages/riscv`](./languages/riscv/README.md) | the RISC-V ISA specification | `c-riscv`, `riscv-btor2`, `riscv-sail` |
| BTOR2     | [`languages/btor2`](./languages/btor2/README.md) | the BTOR2 format (bit-vectors + arrays + a transition system) | `riscv-btor2`, `btor2-smtlib`, `sail-btor2` |
| SMT-LIB   | [`languages/smtlib`](./languages/smtlib/README.md) | the SMT-LIB standard (here: `QF_ABV` and friends) | `btor2-smtlib` |
| Sail      | [`languages/sail`](./languages/sail/README.md)   | the Sail ISA-description language semantics (the RISC-V model) | `riscv-sail`, `sail-btor2` |

The "shared by" column is the sharing graph in [`ARCHITECTURE.md`](./ARCHITECTURE.md)
§6 made concrete: the RISC-V interpreter is written once and used by three
pairs; the BTOR2 interpreter once and used by three.

## Pairs

Briefs: [`pairs/`](./pairs/). All five are *registered*; none are *built* yet.

| Pair | Source → Target | Translator | Target fidelity | Status |
|------|-----------------|------------|-----------------|--------|
| [`c-riscv`](./pairs/c-riscv/README.md)         | C → RISC-V      | a **pinned** C compiler (digest + flags) | `reproducible` (re-established downstream) | registered |
| [`riscv-btor2`](./pairs/riscv-btor2/README.md) | RISC-V → BTOR2  | built **from the RISC-V specification**  | `checked` → `proved` | registered |
| [`btor2-smtlib`](./pairs/btor2-smtlib/README.md)| BTOR2 → SMT-LIB | rule-for-rule bit-vector/array mapping  | `predicted` / `proved` | registered |
| [`riscv-sail`](./pairs/riscv-sail/README.md)   | RISC-V → SAIL   | built **from the RISC-V model in Sail**  | `checked` | registered |
| [`sail-btor2`](./pairs/sail-btor2/README.md)   | SAIL → BTOR2    | Sail-to-transition-system lowering       | `checked` → `proved` | registered |

Fidelity targets are goals stated in each brief, to be backed by evidence
when the pair is built ([`PAIRING.md`](./PAIRING.md) §4); they are not yet
claims.

## Paths

The pairs above form this graph:

```text
   C ──c-riscv──▶ RISC-V ──riscv-btor2─────────▶ BTOR2 ──btor2-smtlib──▶ SMT-LIB
                     │                              ▲
                     └──riscv-sail──▶ SAIL ──sail-btor2──┘
```

Notable routes ([`PATHS.md`](./PATHS.md)):

- **RISC-V → BTOR2, two ways.** `riscv-btor2` (direct, from the spec) and
  `riscv-sail` → `sail-btor2` (via the Sail model). This is the platform's
  first **branch**: two independent encodings of RISC-V into the same
  target, cross-checked to raise fidelity ([`PATHS.md`](./PATHS.md) §4–5).
- **C all the way to a theory solver.** `c-riscv` → (either RISC-V→BTOR2
  route) → `btor2-smtlib`. The opaque compiler head is `reproducible`; its
  fidelity is re-established downstream by the branch and by the far-end
  checks ([`PATHS.md`](./PATHS.md) §3).

## Adding to the registry

A human registers a new **language** by adding `languages/<name>/README.md`
(formal semantics + the interpreter contract) and a new **pair** by adding
`pairs/<source>-<target>/README.md` (the brief, per [`AGENTS.md`](./AGENTS.md)
§1), then triggering its per-pair agent. Update the tables above in the same
change.
