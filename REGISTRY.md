# Registry — languages, interpreters, pairs, and paths

The live state of the platform: which languages are registered (and own the
shared interpreters/solvers/checkers), which pairs exist, the formal model
behind each source language, and which paths the pairs induce. A pair or
language is *registered* when its brief exists here and under
[`languages/`](./languages/) or [`pairs/`](./pairs/); it is *built* when an
agent has delivered it to the [`PAIRING.md`](./PAIRING.md) contract.

## Platform deliverables

Pairs inherit a shared **framework** (registry, cache, commuting-square
oracle, path runner, solver/checker plumbing, coverage harness, path-grader,
player surface) and per-language **interpreters**. Both are **standalone
deliverables, built before pairs** ([`FRAMEWORK.md`](./FRAMEWORK.md)); the
bootstrap order is `framework → interpreters → pairs`. The framework's MVP-1
core and the RISC-V, BTOR2, eBPF, SMT-LIB (QF_ABV + QF_LIA), Wasm (i32+i64 stack), EVM
(bv256-stack), CRN (Petri-net), SMILES, molecular-formula, and Python (pinned
CPython, integer subset) interpreters are now built, with a Sail interpreter
(RV64IMC + an additive AArch64 `ADD`/`SUB`/`MOVZ` + `SUBS`/`CMP` + `B.cond` arm,
interp v0.4) and an AArch64 interpreter (`ADD`/`SUB`/`MOVZ` + `SUBS`/`CMP` +
`B.cond`, interp v0.3) (`gurdy/`); the rest are pending.

| Deliverable | Brief | Status |
|-------------|-------|--------|
| framework (minimum viable, MVP-1) | [`FRAMEWORK.md`](./FRAMEWORK.md) §6 | **partial** — MVP-1 core + path runner + coverage harness + path-grader checks built (`gurdy/`); the `sat`/model-evaluation and `.wit`-replay witness checks are built; the **`proved`-tier unreachability pipeline is wired** (multi-engine corroboration z3+bitwuzla, and bitblast→DRAT via bitwuzla+cadical, `gurdy/solvers/proved.py`) — the independent DRAT check (`drat-trim`/`cake_lpr`) is gated to the dev image; benchmark ingestion / merge-trigger pending |
| RISC-V interpreter | [`languages/riscv`](./languages/riscv/README.md) | **partial** — RV64IMC + ELF loading + `sail_riscv_sim` differential + riscv-tests/-arch-test coverage-slice loader built (`gurdy/languages/riscv/`); in-container acceptance run over the pinned suites pending |
| BTOR2 interpreter | [`languages/btor2`](./languages/btor2/README.md) | **partial** — parser/printer + evaluator (signed div/rem, arrays, bv256) + `.wit` parsing/replay (validated end-to-end against a real `btormc`) built (`gurdy/languages/btor2/`); `btorsim`/HWMCC differentials pending |
| eBPF interpreter | [`languages/ebpf`](./languages/ebpf/README.md) | **partial** (interp v0.3) — ALU/JMP/load-store core + byte-swap (`BPF_END` le/be/bswap ×{16,32,64}) + legacy `ABS`/`IND` packet loads (`B`/`H`/`W`, big-endian, with the out-of-bounds drop edge) built (`gurdy/languages/ebpf/`); CALL pending |
| Sail interpreter | [`languages/sail`](./languages/sail/README.md) | **partial** (interp v0.4) — RV64IM**C** slice (ALU/M/C, control flow, loads/stores) via the Sail-derived `Expr` semantics + an independent RV64C decompressor, wired to the `sail_riscv_sim` differential (gated), **plus an additive AArch64 arm** (`aarch64.py`, dispatched on `isa=aarch64`) covering `ADD`/`SUB` (immediate) + `MOVZ` **plus** the first NZCV write (`SUBS`/`CMP` immediate) and the first conditional control flow (`B.cond`, full condition table) (all 64-bit) for `aarch64-sail` — the v0.3→v0.4 bump adds `SUBS`/`CMP` (the `N`/`Z`/`C`/`V` pack, built as an `Expr` tree) and `B.cond` (a conditional `pc` update, condition predicate as an `Expr` tree), mirroring the `aarch64-btor2` `0.3` widening so the two AArch64→BTOR2 routes decide the same constructs again (covered sets coincide exactly); the RISC-V path is byte-for-byte unchanged (`gurdy/languages/sail/`); auto-deriving from the Sail source and the official `sail-arm` differential pending |
| AArch64 interpreter | [`languages/aarch64`](./languages/aarch64/README.md) | **partial** (interp v0.3) — the `ADD`/`SUB` (immediate) + `MOVZ` ALU family plus the **first NZCV write** (`SUBS`/`CMP` immediate) and **first conditional control flow** (`B.cond`, full condition table), all 64-bit, over `x0`–`x30`/`sp`/`pc`/`nzcv`(`N=3,Z=2,C=1,V=0`)/`halted`, contributed by `aarch64-btor2` as a standalone shared deliverable (`gurdy/languages/aarch64/`); the v0.2→v0.3 bump is strictly **additive** (the `0.1`/`0.2` behavior is byte-for-byte unchanged and the narrower `decode`/`decode_insn` are retained as the `aarch64-sail` rejection gate, so that cross-checked route is undisturbed until its sibling mirrors the new ops; the `0.3` family is decoded by the new `decode_insn_v3`); `SUBS`/`CMP` sets `N`/`Z`/`C`(no-borrow)/`V`(signed-overflow), `B.cond` reads `NZCV` and writes only `pc`; every other A64 instruction hard-aborts (incl. *unconditional* `B`/`BL`, `BC.cond`, addition flag-set `ADDS`); further widening + Sail-ARM/QEMU differential pending |
| Wasm interpreter | [`languages/wasm`](./languages/wasm/README.md) | **partial** (interp v0.4) — integer value-stack core at **two widths** (i32 + i64) over a straight-line body (`gurdy/languages/wasm/`): producers `i32.const` / `i64.const` / `local.get`, the conditional `select` (`0x1b`), the unary comparisons `i32.eqz` (`0x45`) / `i64.eqz` (`0x50`), and the full **binary-operator family at each width** — `{i32,i64}.add`/`sub`/`mul`/`and`/`or`/`xor`, the shifts `shl`/`shr_u`/`shr_s` (amount mod 32 / mod 64), and the comparisons `eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}` (`_s` two's-complement signed; every compare yields i32); the value stack carries both bv32 and bv64 slots (per-slot type tracked); the `0.3`→`0.4` bump was strictly **additive** (binop/compare tables made width-parametric but every i32 result byte-for-byte identical, no existing rule changed, the `wasm-btor2` square re-validated green); every other opcode hard-aborts `unsupported`; `div`/`rem` (trap edge) / rotates / i32↔i64 width conversions / structured control flow / memory / WasmCert anchoring pending |
| EVM interpreter | [`languages/evm`](./languages/evm/README.md) | **partial** (interp v0.4) — bv256 stack machine: the pure stack/arithmetic slice — the full push family `PUSH1`..`PUSH32`, `ADD`/`MUL`/`SUB` (`SUB` top-minus-next, all wrap mod 2²⁵⁶) and the unsigned `DIV`/`MOD` (EVM by-zero = 0), `POP`, the duplications `DUP1`..`DUP16` and the swaps `SWAP1`..`SWAP16`, `STOP` (exceptional halts modeled as defined edges) (`gurdy/languages/evm/`); the `0.3`→`0.4` bump was strictly **additive** (added the full stack-manipulation family — `PUSH3`/`PUSH5..32`, `DUP2..16`, `SWAP1..16` — as generic index-keyed rules; no existing rule changed; the `evm-btor2` square re-validated green); every other opcode hard-aborts `unsupported`; `PUSH0` / the signed `SDIV`/`SMOD` / memory / storage / control flow (`JUMP`/`JUMPI`) pending |
| SMT-LIB interpreter | [`languages/smtlib`](./languages/smtlib/README.md) | **built (QF_ABV + QF_LIA)** (interp v0.2) — s-expression I/O (byte-exact round-trip) + a deterministic model evaluator over two fragments, wired as the shared `I_t` (`gurdy/languages/smtlib/`): the bit-vector/array fragment the bridge emits (`QF_ABV`, reused by `btor2-smtlib` to check a `sat` witness) and now the **linear-integer-arithmetic `QF_LIA`** fragment (`Int` over arbitrary-precision `int`; `+`/`-`/`*`/`div`/`mod`/`abs`; `<=`/`<`/`>=`/`>`/`=`/`distinct`; `ite`; `and`/`or`/`not`/`=>`/`xor`) — a strictly **additive, versioned** bump (`0.1`→`0.2`) that leaves `QF_ABV` value-for-value unchanged (dependents `btor2-smtlib`/`crn-smtlib` re-validated green) and checks a `QF_LIA` `sat` witness, agreeing with `crn-smtlib`'s interpreter-replay verdict end-to-end; `crn-smtlib` consumes it as `smt_model_ok` and `python-smtlib` (built) now wires it as its authoritative SMT-level witness check; the `unsat` proof checkers (`proved` tier) pending |
| CRN interpreter | [`languages/crn`](./languages/crn/README.md) | **partial** — discrete Petri-net stepper over integer markings for **arbitrary-stoichiometry** reactions (`gurdy/languages/crn/`): fires a scheduled reaction when every reactant meets its coefficient, else stutters; a disabled firing is a typed `FiringError` (so unimolecular, bimolecular, and catalysis / multi-product replay identically — the `crn-smtlib` translator, not the interpreter, scopes which classes it bridges; the catalysis widening reused it unchanged, no version bump); CTMC / rate semantics pending |
| SMILES interpreter | [`languages/smiles`](./languages/smiles/README.md) | **partial** (interp `0.3`) — organic-subset **single-bonded tree** of bare atoms `B C N O P S F Cl Br I` with implicit-hydrogen valence filling and nested **branches** `(...)` (`C`, `CCO`, `CN`, `O`, `CCl`, `C(C)C`, `CC(C)C`, …; per-element valence table, degree counts branch bonds) built as the shared `I_s` (`gurdy/languages/smiles/`); every other OpenSMILES construct (and any malformed branch) hard-aborts `unsupported`; multiple bonds / rings / aromatic & bracket atoms pending |
| molecular-formula interpreter | [`languages/molecular-formula`](./languages/molecular-formula/README.md) | **built** — flat Hill-notation `parse` (string → atom multiset) + `to_hill` (canonical, host-independent element order) as the shared `I_t` (`gurdy/languages/molecular_formula/`); nested/charged formulas hard-abort `unsupported` |
| Python interpreter | [`languages/python`](./languages/python/README.md) | **partial** (interp v0.4) — **pinned real CPython restricted to the subset** as the shared source `I_s` (`gurdy/languages/python/`): a loader (`subset.py`) enforces the subset by accepting an AST allow-list (a single integer function — assignment + linear arithmetic + **`if`/`else`** + a **bounded `for i in range(<const>)`** + a **BMC-bounded `while`** + a trailing `assert`) and rejecting everything else with a typed `unsupported: python:<construct>`, and the executor (`eval.py`) runs the accepted program under the host CPython (tag recorded as `PYTHON_PIN`) in a restricted namespace (`__builtins__` emptied: no imports / no I/O), producing a deterministic post-step environment trace (byte-stable across `PYTHONHASHSEED`); the high-level analogue of an ISA differential — the source side is `checked` against CPython as RISC-V is against `sail_riscv_sim`; bumps are **additive** (`0.1`→`0.2` adds `if`/`else`; `0.2`→`0.3` adds the bounded `for`; `0.3`→`0.4` adds the BMC-bounded `while` — guard through CPython, body while it holds, capped at the BMC bound `WHILE_BOUND` = 8 so an unbounded loop can never hang `I_s`); nested loops, `break`/`continue`, `//`/`%`, containers pending (the coverage-ratchet widening) |
| other language interpreters | [`languages/`](./languages/) | registered (not built) |

## Languages

Each language carries a formal semantics and owns the source/target
interpreter shared by every pair that touches it
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §6). Briefs: [`languages/`](./languages/).

| Language | Brief | Formal semantics (source of truth) | Interpreter shared by |
|----------|-------|------------------------------------|-----------------------|
| C        | [`c`](./languages/c/README.md) | C abstract machine (ISO C) | `c-riscv` |
| RISC-V   | [`riscv`](./languages/riscv/README.md) | RISC-V ISA specification | `c-riscv`, `riscv-btor2`, `riscv-sail` |
| AArch64  | [`aarch64`](./languages/aarch64/README.md) | Arm ARM (A-profile) | `aarch64-btor2`, `aarch64-sail` |
| WebAssembly | [`wasm`](./languages/wasm/README.md) | the official Wasm formal semantics | `wasm-btor2` |
| eBPF     | [`ebpf`](./languages/ebpf/README.md) | the eBPF ISA | `ebpf-btor2` |
| EVM      | [`evm`](./languages/evm/README.md) | EVM execution semantics | `evm-btor2` |
| BTOR2    | [`btor2`](./languages/btor2/README.md) | BTOR2 transition systems (bit-vectors + arrays) | `riscv-btor2`, `sail-btor2`, `aarch64-btor2`, `wasm-btor2`, `ebpf-btor2`, `evm-btor2` |
| SMT-LIB  | [`smtlib`](./languages/smtlib/README.md) | the SMT-LIB standard (`QF_ABV`/`QF_LIA`…) | `btor2-smtlib`, `crn-smtlib`, `python-smtlib` (partial) |
| Sail     | [`sail`](./languages/sail/README.md) | Sail semantics (RISC-V & Arm models) | `riscv-sail`, `sail-btor2`, `aarch64-sail` |
| CRN      | [`crn`](./languages/crn/README.md) | Petri-net / CTMC mass-action semantics | `crn-smtlib` |
| SMILES   | [`smiles`](./languages/smiles/README.md) | OpenSMILES molecular-graph semantics | `smiles-formula` |
| molecular formula | [`molecular-formula`](./languages/molecular-formula/README.md) | atom multiset (Hill notation) | `smiles-formula` |
| Python (subset) | [`python`](./languages/python/README.md) | small-step subset semantics (pinned CPython as the oracle) | `python-smtlib` (partial) |

The "shared by" column is the sharing graph of
[`ARCHITECTURE.md`](./ARCHITECTURE.md) §6 made concrete: the RISC-V
interpreter is written once and used by three pairs; the BTOR2 interpreter
once and used by six.

## Formal models per source language

Which source languages have a **Sail** model (so a Sail-mediated
fidelity-raising branch like `riscv-sail` → `sail-btor2` is possible), and
the recommended model for those that do not ([`ARCHITECTURE.md`](./ARCHITECTURE.md)
§7, [`PATHS.md`](./PATHS.md) §4):

| Source | Sail model? | Recommended formal model / oracle | Branch implication |
|--------|-------------|------------------------------------|--------------------|
| RISC-V  | ✅ official `sail-riscv` (RISC-V Foundation) | the Sail RISC-V model | **partial** (RV64IMC): `riscv-sail` → `sail-btor2` built and cross-checked against the direct route |
| AArch64 | ✅ `sail-arm` (auto-translated from Arm's ASL); `sail-morello` | the Sail ARM model | **partial** (`ADD`/`SUB`/`MOVZ` + `SUBS`/`CMP` + `B.cond`): `aarch64-sail` → `sail-btor2` built, cross-checkable against the direct route |
| WebAssembly | ❌ (not an ISA) | official Wasm formal semantics; **WasmCert-Isabelle/Coq**; **KWasm** | route via WasmCert/KWasm as a second path / source oracle |
| eBPF | ❌ | **CertrBPF / CertFC** (Coq); **Jitterbug** (Rosette) | CertrBPF as source oracle; optional model route |
| EVM | ❌ | **KEVM** (K); **eth-isabelle** (Lem); **EVM-Dafny** | KEVM as source oracle; optional model route |
| CRN | ❌ (not an ISA) | Petri-net / CTMC semantics; **PRISM/STORM**, **Maude** | the semantics *is* the model; PRISM/Maude as oracle |
| SMILES | ❌ | **OpenSMILES** graph semantics; **RDKit** / **InChI** | RDKit/InChI as oracle |
| Python | ❌ | **K-Python** (Guth, K framework, tested vs CPython) | K-Python (subset) as oracle |

Sail models exist for further ISAs not yet sourced here — **MIPS** /
CHERI-MIPS, **CHERI-RISC-V** / CHERIoT, **x86** (translated from the ACL2
`x86isa` model), and fragments of **IBM Power** — available if any becomes a
source. Per-language detail and citations are in each
[`languages/`](./languages/) brief.

## Reasoning targets — solvers and witness checkers

BTOR2 and SMT-LIB are reasoning languages: each owns, in addition to an
interpreter, a shared **solver** inventory (the oracle that decides) and a
shared **witness-checker** inventory (the independent re-validator). See
[`SOLVERS.md`](./SOLVERS.md); details in the language briefs.

| Reasoning language | Solvers (decide) | Witness checkers (verify) |
|--------------------|------------------|---------------------------|
| BTOR2   | BtorMC, Pono, AVR | interpreter replay (`.wit`), independent-engine invariant / k-induction re-discharge, `certifaiger`-style certificate check |
| SMT-LIB | Bitwuzla, Z3, cvc5, Yices2 | model evaluation, Carcara (Alethe), LFSC, `cake_lpr` (verified LRAT) |

Both inventories are shared by every pair targeting the language; a pair
wires none of its own.

*Wired so far:* the SMT-LIB **solver inventory** (`gurdy/solvers/inventory.py`,
SOLVERS.md §8) registers **z3**, **bitwuzla**, **boolector**, **cvc5**,
**yices2** — z3/bitwuzla/boolector are host-validated, cvc5/yices2 are thin gated
adapters that activate when their binary is present (`gurdy/solvers/smt_cli.py`).
A `sat` model is checked by the shared evaluator; on the BTOR2 side
**btormc**/**pono** decide reachability and a `.wit` is checked by interpreter
replay. The **`proved` tier** for `unreachable` (`gurdy/solvers/proved.py`)
**corroborates across every available engine** (flagging any *disagreement* as a
translator-or-solver bug, §7) and produces a bit-blasted **DRAT** certificate
(bitwuzla→CNF, cadical→DRAT); its independent checker (`drat-trim`/`cake_lpr`)
and **AVR** (BTOR2) remain gated to / deferred for the dev image
([#2](https://github.com/cksystemsgroup/hurdy-gurdy/issues/2)).

## Pairs

Briefs: [`pairs/`](./pairs/). Fidelity targets are goals to be backed by
evidence when the pair is built ([`PAIRING.md`](./PAIRING.md) §4), not yet
claims.

| Pair | Source → Target | Translator | Fidelity target | Status |
|------|-----------------|------------|-----------------|--------|
| [`c-riscv`](./pairs/c-riscv/README.md)         | C → RISC-V      | a **pinned** C compiler | `reproducible` (re-established) | **partial** (reproducible) |
| [`riscv-btor2`](./pairs/riscv-btor2/README.md) | RISC-V → BTOR2  | from the RISC-V spec | `checked` → `proved` | **partial** (RV64IMC) |
| [`aarch64-btor2`](./pairs/aarch64-btor2/README.md) | AArch64 → BTOR2 | from the Arm spec | `checked` → `proved` | **partial** (ALU + flag-set + cond-branch: `ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `B.cond`; 11/15 probes, interp v0.3) |
| [`wasm-btor2`](./pairs/wasm-btor2/README.md)   | WebAssembly → BTOR2 | from the Wasm spec | `checked` | **partial** (integer value-stack core at **two widths**: `i32.const`/`i64.const`/`local.get`/`select`/`i32.eqz`/`i64.eqz` + the full binop family at i32 *and* i64 — arith/bitwise/shift (mod-32 / mod-64) + signed&unsigned compares (yielding i32); per-slot value-type tracking (bv32+bv64 slots); 44/44 in-scope, Wasm interp v0.4, 31 constructs typed `unsupported`) |
| [`ebpf-btor2`](./pairs/ebpf-btor2/README.md)   | eBPF → BTOR2    | from the eBPF spec | `checked` | **partial** (ALU/JMP/mem + byte-swap + ABS/IND packet loads; 124/124 composed) |
| [`evm-btor2`](./pairs/evm-btor2/README.md)     | EVM → BTOR2     | from the EVM spec (bv256) | `checked` | **partial** (pure stack/arithmetic slice: full PUSH1..32/DUP1..16/SWAP1..16 family, ADD/MUL/SUB, DIV/MOD, POP, STOP; 71/144 opcodes; EVM interp v0.4) |
| [`btor2-smtlib`](./pairs/btor2-smtlib/README.md)| BTOR2 → SMT-LIB | rule-for-rule mapping | `predicted` / `proved` | **partial** (unroll + z3 + array witnesses; 56/56 operator inventory; shared SMT model check; `reach`/`prove` — `prove` corroborates z3+bitwuzla and emits a DRAT cert, checker gated) |
| [`crn-smtlib`](./pairs/crn-smtlib/README.md)   | CRN → SMT-LIB   | schema-determined unrolling | `predicted` | **partial** (uni- + bimolecular + catalysis / multi-product + synthesis / degradation: `A -> B`, `A + B -> C`, `2 A -> B`, `A -> 2 B`, `A -> B + C`, `0 -> A`, `A -> 0` → `QF_LIA` unroll + z3 + firing-flag witness replay, `smt_model_ok` agrees with replay; 7/10 reaction classes, rest typed `unsupported`) |
| [`riscv-sail`](./pairs/riscv-sail/README.md)   | RISC-V → Sail   | from the RISC-V Sail model | `checked` | **partial** (RV64IMC) |
| [`sail-btor2`](./pairs/sail-btor2/README.md)   | Sail → BTOR2    | Sail → transition system | `checked` → `proved` | **partial** (RV64IMC) |
| [`aarch64-sail`](./pairs/aarch64-sail/README.md) | AArch64 → Sail | from the Arm Sail model | `checked` | **partial** (ALU + flag-set + cond-branch: `ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `B.cond`; 11/15 probes, Sail interp v0.4) |
| [`smiles-formula`](./pairs/smiles-formula/README.md) | SMILES → molecular formula | schema-determined (compile pair) | `predicted` | **partial** (organic-subset single-bonded tree, heteroatoms `B C N O P S F Cl Br I` + nested **branches** `(...)`; **6/17** constructs, rest typed `unsupported`; smiles interp `0.3`) |
| [`python-smtlib`](./pairs/python-smtlib/README.md) | Python → SMT-LIB | `QF_LIA` SSA lowering (CPython oracle) | `predicted` / `checked` | **partial** (slice 4: straight-line integer function + **`if`/`else`** + a **bounded loop** `for i in range(<const>)` + a **BMC-bounded loop** `while <cond>` — assignment + linear arithmetic + an `ite` SSA branch merge + a fully-unrolled compile-time-constant `for` + a `while` unrolled to the fixed bound `K` = 8 with a terminated-within-`K` assertion + a trailing `assert` → `QF_LIA` + z3 + input-assignment witness replayed through pinned CPython down the taken branch / through the unrolled loop; **5/19 constructs** covered, up from 4/18 — `while` (BMC-bounded) ratcheted in (`While` leaves the gap), `break`/`continue` itemized; rest typed `unsupported`) |

## Coverage and status

A pair's status reflects **measured coverage**, not a self-declaration
([`BENCHMARKS.md`](./BENCHMARKS.md)): `registered` → `partial (<coverage>)` →
`built`. `built` requires meeting the brief's coverage target (construct
inventory + public suite) with every unsupported construct hard-aborting.
Path status — branch-agreement and composed coverage per route — is computed
by the merge-triggered **path-grader agent** ([`AGENTS.md`](./AGENTS.md) §7)
and recorded against the routes below.

## Paths

The pairs form two reasoning **hubs** and a bridge between them
([`PATHS.md`](./PATHS.md)):

```text
   C ─c-riscv─▶ RISC-V ─┬─riscv-btor2──────────────▶ BTOR2 ─btor2-smtlib─▶ SMT-LIB
                        └─riscv-sail─▶ SAIL ─sail-btor2─▶ ▲                  ▲
                                                          │                  │
        AArch64 ─aarch64-btor2─▶ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┤        CRN ─crn-smtlib─┘
        WebAssembly ─wasm-btor2─▶ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┤
        eBPF ─ebpf-btor2─▶ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┤
        EVM ─evm-btor2─▶ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```

- **The BTOR2 hub.** Six front-ends (RISC-V, Sail, AArch64, Wasm, eBPF, EVM)
  reach BTOR2; `btor2-smtlib` bridges BTOR2 to the SMT-LIB hub.
- **The SMT-LIB hub.** Reached via the BTOR2 bridge and directly from CRN
  (and, as a candidate, Python).
- **Two branches.** RISC-V reaches BTOR2 two ways — directly (`riscv-btor2`)
  and via Sail (`riscv-sail` → `sail-btor2`); AArch64 likewise — directly
  (`aarch64-btor2`) and via the Arm Sail model (`aarch64-sail` →
  `sail-btor2`). Each branch is cross-checked to raise fidelity
  ([`PATHS.md`](./PATHS.md) §4–5).
- **Solve-step corroboration.** Every BTOR2-targeting front-end can be
  decided native-vs-bridged through `btor2-smtlib`
  ([`SOLVERS.md`](./SOLVERS.md) §7).
- **Composed coverage** (the path-grader's third measurement; `gurdy
  path-coverage <src> <dst>`). Computed today: `riscv → smtlib` **96/96** (direct)
  and **95/95** (via Sail — now RV64IMC), and `ebpf → smtlib` **124/124** — every front-end
  construct that a pair lowers survives end-to-end to SMT-LIB, with any gap
  localized to the rejecting hop ([`gurdy/core/grade.py`](./gurdy/core/grade.py)).
- **Branch agreement** (now load-bearing). RISC-V reaches BTOR2 two *independent*
  ways — directly (`riscv-btor2`) and via the Sail-derived model
  (`riscv-sail` → `sail-btor2`); the path-grader decides the same reachability
  question along both `riscv → smtlib` routes and confirms they agree
  (REACHABLE/UNREACHABLE), the fidelity cross-check the design exists for
  ([`PATHS.md`](./PATHS.md) §4-5). This now reaches the C head: a property
  about a gcc-compiled C program is decided over both `c → smtlib` routes
  (direct and Sail-mediated) and required to agree.

## Adding to the registry

A human registers a new **language** by adding `languages/<name>/README.md`
(formal semantics + interpreter contract; for reasoning targets, the solver
and checker inventories) and a new **pair** by adding
`pairs/<source>-<target>/README.md` (the brief, per [`AGENTS.md`](./AGENTS.md)
§1), then triggering its per-pair agent. Update the tables above in the same
change.
