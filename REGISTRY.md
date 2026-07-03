# Registry — languages, interpreters, pairs, and routes

The live state of the platform: which languages are registered (and own the
shared interpreters/solvers/checkers), which pairs exist, the formal model
behind each source language, and which routes the pairs induce. A pair or
language is *registered* when its brief exists here and under
[`languages/`](./languages/) or [`pairs/`](./pairs/); it is *built* when an
agent has delivered it to the [`PAIRING.md`](./PAIRING.md) contract.

## Platform deliverables

Pairs inherit a shared **framework** (registry, cache, commuting-square
oracle, route runner, solver/checker plumbing, coverage harness, route-grader,
player surface) and per-language **interpreters**. Both are **standalone
deliverables, built before pairs** ([`FRAMEWORK.md`](./FRAMEWORK.md)); the
bootstrap order is `framework → interpreters → pairs`. The framework's MVP-1
core and the RISC-V, BTOR2, eBPF, SMT-LIB (QF_ABV + QF_LIA), Wasm (i32+i64 stack), EVM
(bv256-stack), CRN (Petri-net), SMILES, molecular-formula, and Python (pinned
CPython, integer subset) interpreters are now built, with a Sail interpreter
(RV64IMC + an additive AArch64 `ADD`/`SUB`/`MOVZ` + `SUBS`/`CMP` + `ADDS`/`CMN` +
`B.cond` + `B`/`BL` + `LDR`/`STR` + the 32-bit W-register ALU/flag forms arm, interp
v0.7) and an AArch64 interpreter
(`ADD`/`SUB`/`MOVZ` + `SUBS`/`CMP` + `ADDS`/`CMN` + `B.cond` + `B`/`BL` +
`LDR`/`STR` + the 32-bit W-register ALU/flag forms, interp v0.6) (`gurdy/`); the
rest are pending.

| Deliverable | Brief | Status |
|-------------|-------|--------|
| framework (minimum viable, MVP-1) | [`FRAMEWORK.md`](./FRAMEWORK.md) §6 | **partial** — MVP-1 core + route runner + coverage harness + route-grader checks built (`gurdy/`); the `sat`/model-evaluation and `.wit`-replay witness checks are built; the **`proved`-tier unreachability pipeline is wired end-to-end** (multi-engine corroboration z3+bitwuzla, and bitblast→DRAT via bitwuzla+cadical, `gurdy/solvers/proved.py`) — the **independent DRAT check runs** wherever a `drat-trim` binary is on `PATH` (validated on host 2026-07-02 with `drat-trim` @ `2e3b2dc`, positive + negative controls in `tests/test_proved.py`; the negative control caught and fixed a status-line parse defect in `check_drat`), and the **verified checker rung is live**: the DRAT is elaborated to LRAT (`drat-trim`, untrusted) and re-validated by `cake_lpr`, the formally verified CakeML checker (host-native ARMv8 build @ `a4323b2`, validated 2026-07-03 with its own negative controls — note `cake_lpr` exits 0 on failure, only the `s VERIFIED UNSAT` line signals success); benchmark ingestion / merge-trigger pending |
| RISC-V interpreter | [`languages/riscv`](./languages/riscv/README.md) | **partial** — RV64IMC + ELF loading + `sail_riscv_sim` differential + riscv-tests/-arch-test coverage-slice loader built (`gurdy/languages/riscv/`); in-container acceptance run over the pinned suites pending |
| BTOR2 interpreter | [`languages/btor2`](./languages/btor2/README.md) | **partial** — parser/printer + evaluator (signed div/rem, arrays, bv256) + `.wit` parsing/replay (validated end-to-end against a real `btormc`) built (`gurdy/languages/btor2/`); `btorsim`/HWMCC differentials pending |
| eBPF interpreter | [`languages/ebpf`](./languages/ebpf/README.md) | **partial** (interp v0.4) — ALU/JMP/load-store core + byte-swap (`BPF_END` le/be/bswap ×{16,32,64}) + legacy `ABS`/`IND` packet loads (`B`/`H`/`W`, big-endian, with the out-of-bounds drop edge) + `CALL` (helper-return-as-input: `r0`+clobbered `r1`–`r5` fresh inputs, `r6`–`r10` preserved; every helper id modeled uniformly) built (`gurdy/languages/ebpf/`); in-scope construct set complete |
| Sail interpreter | [`languages/sail`](./languages/sail/README.md) | **partial** (interp v0.7) — RV64IM**C** slice (ALU/M/C, control flow, loads/stores) via the Sail-derived `Expr` semantics + an independent RV64C decompressor, wired to the `sail_riscv_sim` differential (gated), **plus an additive AArch64 arm** (`aarch64.py`, dispatched on `isa=aarch64`) covering `ADD`/`SUB` (immediate) + `MOVZ` **plus** the NZCV writes (`SUBS`/`CMP` **and** `ADDS`/`CMN` immediate), the conditional **and** unconditional control flow (`B.cond`, full condition table; `B`/`BL`), the first memory access — the 64-bit unsigned-offset `LDR`/`STR` over a byte-addressed little-endian memory (a Python byte map; the `Expr` IR is QF_BV-only, so only the LE byte-assembly is a Sail-derived `Expr` tree) with the `m0`–`m63` memory-window observable — **and the 32-bit (W-register) forms** of the ALU/flag immediate ops (`ADD`/`SUB`/`MOVZ` W and `SUBS`/`CMP`/`ADDS`/`CMN` W) for `aarch64-sail` — the v0.3→v0.4 bump added `SUBS`/`CMP` (the `N`/`Z`/`C`/`V` pack) and `B.cond`; the v0.4→v0.5 bump added the unconditional `B`/`BL` (always taken; `BL` writes `x30 := pc+4`) and the addition flag-set `ADDS`/`CMN` (the addition `C`(carry-out)/`V`(signed-overflow), distinct from `SUBS`'s); the v0.5→v0.6 bump added the 64-bit `LDR`/`STR` + the `m{i}` window; the v0.6→v0.7 bump adds the **32-bit W forms** — the op computes on the low 32 bits (`slice(a,31,0)`), the bv32 result **zero-extends** into `Xd` (upper 32 bits = 0; vs RV64's `*W` sign-extend), and the `SUBS`/`ADDS` W flags are packed at 32-bit width — built as `Expr` trees and switching the A64 decoder gate to `decode_insn_v6`, mirroring the `aarch64-btor2` `0.5`→`0.6` widening so the two AArch64→BTOR2 routes decide the same constructs again (covered sets + projections coincide exactly, 27/33); the RISC-V arm is byte-for-byte unchanged (`gurdy/languages/sail/`); auto-deriving from the Sail source and the official `sail-arm` differential pending |
| AArch64 interpreter | [`languages/aarch64`](./languages/aarch64/README.md) | **partial** (interp v0.6) — the `ADD`/`SUB` (immediate) + `MOVZ` ALU family, the NZCV writes (`SUBS`/`CMP` **and** `ADDS`/`CMN` immediate), the conditional **and** unconditional control flow (`B.cond`, full condition table; `B`/`BL`), the first memory access — the 64-bit unsigned-offset `LDR`/`STR` over a byte-addressed little-endian memory — **and now the 32-bit (W-register) forms** of the ALU/flag immediate ops (`ADD`/`SUB`/`MOVZ` W and `SUBS`/`CMP`/`ADDS`/`CMN` W), over `x0`–`x30`/`sp`/`pc`/`nzcv`(`N=3,Z=2,C=1,V=0`)/`m0`–`m63`(the 64-byte memory window)/`halted`, contributed by `aarch64-btor2` as a standalone shared deliverable (`gurdy/languages/aarch64/`); the v0.5→v0.6 bump is strictly **additive** (the `0.1`–`0.5` behavior is byte-for-byte unchanged and the narrower `decode`/`decode_insn`/`decode_insn_v3`/`decode_insn_v4`/`decode_insn_v5` are retained as the `aarch64-sail` rejection gate, so that cross-checked route is undisturbed until its sibling mirrors the new ops; the `0.6` W forms are decoded by the new `decode_insn_v6`); the 32-bit W forms compute on the **low 32 bits**, **zero-extend** the result into the 64-bit `Xd` (vs RV64's `*W` sign-extend), and set the flags at **32-bit** width (`N`=bit31, `Z`/`C`/`V` from the 32-bit add/subtract); `LDR`/`STR` use the unsigned-offset form (`imm = imm12*8`, LE), base field 31 = `SP`, transfer field 31 = `XZR` (load discarded / store 0); `SUBS`/`CMP` sets `N`/`Z`/`C`(no-borrow)/`V`(signed-overflow) and `ADDS`/`CMN` sets `N`/`Z`/`C`(unsigned carry-out)/`V`(signed-overflow); `B`/`BL` always taken (`BL` writes `x30 := pc+4`); every other A64 instruction hard-aborts (incl. `BC.cond`, `MOVN`/`MOVK`, reserved 32-bit `MOVZ` hw≥2, `LDRB`/`STRB`, 32-bit `LDR`/`STR`, other addressing modes); further widening + Sail-ARM/QEMU differential pending |
| Wasm interpreter | [`languages/wasm`](./languages/wasm/README.md) | **partial** (interp v0.6) — integer value-stack core at **two widths** (i32 + i64) over a single function body (`gurdy/languages/wasm/`): producers `i32.const` / `i64.const` / `local.get`, the local store `local.set` (`0x21`), the conditional `select` (`0x1b`), the unary comparisons `i32.eqz` (`0x45`) / `i64.eqz` (`0x50`), the full **binary-operator family at each width** — `{i32,i64}.add`/`sub`/`mul`/`and`/`or`/`xor`, the shifts `shl`/`shr_u`/`shr_s` (amount mod 32 / mod 64), and the comparisons `eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}` (`_s` two's-complement signed; every compare yields i32), the **division / remainder family** `{i32,i64}.div_s`/`div_u`/`rem_s`/`rem_u` with the Wasm **trap** edge (a `trapped` observable: a zero divisor — and `div_s` signed overflow `INT_MIN / −1` — traps, a *defined* halt distinct from the typed `unsupported` abort; `rem_s` of `INT_MIN % −1` is `0`, no trap), and the **structured conditional** `if <blocktype> <then> [else <else>] end` (`0x04`/`0x05`/`0x0b`) — a body item executed as one step (pop an i32 condition, run the taken arm; the Wasm validation discipline — i32 condition, both arms balance to the block result, no `else` only for a void block — is enforced or a typed `unsupported` aborts; a nested `if` is allowed, while `block`/`loop`/`br`/`br_if`/`br_table` stay out of scope); the value stack carries both bv32 and bv64 slots (per-slot type tracked) and locals are now mutable; the `0.5`→`0.6` bump was strictly **additive** (no existing rule's value changed, a body with no `if`/`local.set` runs byte-for-byte as before, the `wasm-btor2` square re-validated green); every other opcode hard-aborts `unsupported`; rotates / i32↔i64 width conversions / real branching+iteration / memory / WasmCert anchoring pending |
| EVM interpreter | [`languages/evm`](./languages/evm/README.md) | **partial** (interp v0.9) — bv256 stack machine: the stack/arithmetic slice — the full push family `PUSH1`..`PUSH32` plus `PUSH0` (constant-0 push), `ADD`/`MUL`/`SUB` (`SUB` top-minus-next, all wrap mod 2²⁵⁶), the unsigned `DIV`/`MOD` and the signed `SDIV`/`SMOD` (EVM by-zero = 0; `SDIV` with the `INT_MIN/-1` wrap; truncating, sign-of-dividend), `POP`, the duplications `DUP1`..`DUP16` and the swaps `SWAP1`..`SWAP16`, `STOP` — the byte-addressed memory ops `MLOAD`/`MSTORE`/`MSTORE8` over a zero-init unbounded byte map (32-byte big-endian word; observable = a 64-byte window `m0..m63`) — the persistent storage ops `SLOAD`/`SSTORE` over a zero-init 256-bit-key → 256-bit-value map (single word read/write; observable = an 8-key window `s_at_0..s_at_7`) — the control-flow ops `JUMP`/`JUMPI`/`JUMPDEST`/`PC` (the first non-linear control flow: a dynamic, popped destination resolved against the statically-scanned `JUMPDEST` set; an invalid jump is an exceptional halt) — **plus the terminal/halt ops `RETURN`/`REVERT`/`INVALID`** (the first halts that carry a *why*: a `status` observable — running / success / revert / exceptional — alongside `halted`; `RETURN`/`REVERT` pop offset+length, the data range already in the memory window) (`gurdy/languages/evm/`); the `0.8`→`0.9` bump was strictly **additive** (added `PUSH0`/`RETURN`/`REVERT`/`INVALID` + the `status` observable; no existing rule changed — `STOP`/off-the-end stay success, the existing exceptional edges now also record `status`; the `evm-btor2` square re-validated green); every other opcode hard-aborts `unsupported`; `MSIZE` / gas / `CALL`/`CREATE`/`LOG` pending |
| SMT-LIB interpreter | [`languages/smtlib`](./languages/smtlib/README.md) | **built (QF_ABV + QF_LIA)** (interp v0.2) — s-expression I/O (byte-exact round-trip) + a deterministic model evaluator over two fragments, wired as the shared `I_t` (`gurdy/languages/smtlib/`): the bit-vector/array fragment the bridge emits (`QF_ABV`, reused by `btor2-smtlib` to check a `sat` witness) and now the **linear-integer-arithmetic `QF_LIA`** fragment (`Int` over arbitrary-precision `int`; `+`/`-`/`*`/`div`/`mod`/`abs`; `<=`/`<`/`>=`/`>`/`=`/`distinct`; `ite`; `and`/`or`/`not`/`=>`/`xor`) — a strictly **additive, versioned** bump (`0.1`→`0.2`) that leaves `QF_ABV` value-for-value unchanged (dependents `btor2-smtlib`/`crn-smtlib` re-validated green) and checks a `QF_LIA` `sat` witness, agreeing with `crn-smtlib`'s interpreter-replay verdict end-to-end; `crn-smtlib` consumes it as `smt_model_ok` and `python-smtlib` (built) now wires it as its authoritative SMT-level witness check; the `unsat` proof checkers (`proved` tier) pending |
| CRN interpreter | [`languages/crn`](./languages/crn/README.md) | **partial** — discrete Petri-net stepper over integer markings for **arbitrary-stoichiometry** reactions (`gurdy/languages/crn/`): fires a scheduled reaction (named by 0-based index, so a multi-reaction schedule selects which one fires each step) when every reactant meets its coefficient, else stutters; a disabled / out-of-range firing is a typed `FiringError` (so unimolecular, bimolecular, catalysis / multi-product, self-loop (net-zero), multi-reaction and empty-network replay identically — the `crn-smtlib` translator, not the interpreter, scopes which classes it bridges; every widening incl. multiple-reactions / self-loop / empty-network reused it unchanged, no version bump); CTMC / rate semantics pending |
| SMILES interpreter | [`languages/smiles`](./languages/smiles/README.md) | **partial** (interp `0.6`) — organic-subset **graph of single / double / triple bonds — chains, branches, rings — plus bracket atoms** over bare atoms `B C N O P S F Cl Br I` with implicit-hydrogen valence filling, nested **branches** `(...)`, **double** `=` / **triple** `#` (and explicit single `-`) bonds, **ring-closure bonds** (a digit `1`-`9` or `%nn` label), **and bracket atoms** `[...]` (any element, explicit H; isotope/charge/chirality/class parsed but not counted) (`C`, `CCO`, `C(C)C`, `C=C`, `C#C`, `O=C=O`, `C1CCCCC1`, `O1CCOCC1`, `[NH4+]`, `[Se]`, `[13C]`, `C[N+]C`, …; per-element valence table for bare atoms, no implicit H for bracket atoms) built as the shared `I_s` (`gurdy/languages/smiles/`); every other OpenSMILES construct (and any malformed branch / dangling or valence-exceeding bond / malformed ring closure / malformed bracket) hard-aborts `unsupported`; aromatic atoms (bare & in brackets), stereo bonds & disconnection pending |
| molecular-formula interpreter | [`languages/molecular-formula`](./languages/molecular-formula/README.md) | **built** — flat Hill-notation `parse` (string → atom multiset) + `to_hill` (canonical, host-independent element order) as the shared `I_t` (`gurdy/languages/molecular_formula/`); nested/charged formulas hard-abort `unsupported` |
| Python interpreter | [`languages/python`](./languages/python/README.md) | **partial** (interp v0.6) — **pinned real CPython restricted to the subset** as the shared source `I_s` (`gurdy/languages/python/`): a loader (`subset.py`) enforces the subset by accepting an AST allow-list (a single integer function — assignment + linear arithmetic + **`if`/`else`** + a **bounded `for i in range(<const>)`** + a **BMC-bounded `while`** + **nested loops** (a loop in another loop / in an `if` arm in a loop, within the depth/size caps `MAX_LOOP_DEPTH` = 2 / `MAX_UNROLL_PRODUCT` = 64) + **fixed-length integer lists** (a list of static length `L` ≤ `MAX_LIST_LEN` = 16 — literal, const / dynamic index read & write, `len`) + a trailing `assert`) and rejecting everything else with a typed `unsupported: python:<construct>`, and the executor (`eval.py`) runs the accepted program under the host CPython (tag recorded as `PYTHON_PIN`) in a restricted namespace (`__builtins__` emptied except the admitted `len`: no imports / no I/O), producing a deterministic post-step environment trace (byte-stable across `PYTHONHASHSEED`); the high-level analogue of an ISA differential — the source side is `checked` against CPython as RISC-V is against `sail_riscv_sim`; bumps are **additive** (`0.1`→`0.2` adds `if`/`else`; `0.2`→`0.3` adds the bounded `for`; `0.3`→`0.4` adds the BMC-bounded `while` — guard through CPython, body while it holds, capped at the BMC bound `WHILE_BOUND` = 8 so an unbounded loop can never hang `I_s`; `0.4`→`0.5` adds **nested loops** — CPython runs them natively; `0.5`→`0.6` adds **fixed-length integer lists** — CPython runs the real list, the loader admits the list AST nodes within `MAX_LIST_LEN`, an out-of-range index recorded as a defined error); a loop nested past the caps (`nesting-too-deep`), `break`/`continue`, `//`/`%`, variable-length / nested lists pending (the coverage-ratchet widening) |
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
§7, [`ROUTES.md`](./ROUTES.md) §4):

| Source | Sail model? | Recommended formal model / oracle | Branch implication |
|--------|-------------|------------------------------------|--------------------|
| RISC-V  | ✅ official `sail-riscv` (RISC-V Foundation) | the Sail RISC-V model | **partial** (RV64IMC): `riscv-sail` → `sail-btor2` built and cross-checked against the direct route |
| AArch64 | ✅ `sail-arm` (auto-translated from Arm's ASL); `sail-morello` | the Sail ARM model | **partial** (`ADD`/`SUB`/`MOVZ` + `SUBS`/`CMP` + `ADDS`/`CMN` + `B.cond` + `B`/`BL` + `LDR`/`STR` + the 32-bit W forms): `aarch64-sail` → `sail-btor2` built end-to-end (the `sail-btor2` A64 arm landed) and **cross-checked** against the direct route — composed coverage 27/33, solver-level branch agreement |
| WebAssembly | ❌ (not an ISA) | official Wasm formal semantics; **WasmCert-Isabelle/Coq**; **KWasm** | route via WasmCert/KWasm as a second route / source oracle |
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
| [`aarch64-btor2`](./pairs/aarch64-btor2/README.md) | AArch64 → BTOR2 | from the Arm spec | `checked` → `proved` | **partial** (ALU + flag-set + branches + memory + 32-bit W forms: `ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `ADDS`/`CMN`, `B.cond`, `B`/`BL`, `LDR`/`STR`, and their 32-bit W variants; 27/33 probes, interp v0.6) |
| [`wasm-btor2`](./pairs/wasm-btor2/README.md)   | WebAssembly → BTOR2 | from the Wasm spec | `checked` | **partial** (integer value-stack core at **two widths**: `i32.const`/`i64.const`/`local.get`/`local.set`/`select`/`i32.eqz`/`i64.eqz` + the full binop family at i32 *and* i64 — arith/bitwise/shift (mod-32 / mod-64) + signed&unsigned compares (yielding i32) — the div/rem family `{i32,i64}.div_s`/`div_u`/`rem_s`/`rem_u` with the Wasm **trap** edge (zero divisor / `div_s` `INT_MIN/−1` overflow set a `trapped` observable, a defined halt; `rem_s INT_MIN%−1 = 0`, no trap), **and the structured conditional** `if <blocktype> <then> [else <else>] end` — lowered by the value-stack **branch-merge** (both arms evaluated over a copy of the incoming static stack, joined per slot/local with `ite(cond≠0, then, else)`); validation discipline (i32 condition, both arms balance to the block result, no `else` only for void) enforced or a typed `unsupported`; nested `if` allowed; `block`/`loop`/`br`/`br_if`/`br_table` still `unsupported`; per-slot value-type tracking (bv32+bv64 slots) + mutable locals; 54/54 in-scope, Wasm interp v0.6, 21 constructs typed `unsupported`) |
| [`ebpf-btor2`](./pairs/ebpf-btor2/README.md)   | eBPF → BTOR2    | from the eBPF spec | `checked` | **partial** (ALU/JMP/mem + byte-swap + ABS/IND packet loads + CALL; 126/126; in-scope set complete) |
| [`evm-btor2`](./pairs/evm-btor2/README.md)     | EVM → BTOR2     | from the EVM spec (bv256 + arrays) | `checked` | **partial** (stack/arithmetic slice: full PUSH0/PUSH1..32/DUP1..16/SWAP1..16 family, ADD/MUL/SUB, DIV/MOD, SDIV/SMOD, POP, STOP; byte-addressed memory MLOAD/MSTORE/MSTORE8 over a BTOR2 `Array bv256 bv8` (64-byte window `m0..m63`); persistent storage SLOAD/SSTORE over an `Array bv256 bv256` (8-key window `s_at_0..s_at_7`); control flow JUMP/JUMPI/JUMPDEST/PC (dynamic pc as an ITE over the static JUMPDEST set); **plus terminal halts RETURN/REVERT/INVALID** (a `status` observable: running/success/revert/exceptional); 86/144 opcodes; EVM interp v0.9) |
| [`btor2-smtlib`](./pairs/btor2-smtlib/README.md)| BTOR2 → SMT-LIB | rule-for-rule mapping | `predicted` / `proved` | **partial** (unroll + z3 + array witnesses; 56/56 operator inventory; shared SMT model check; `reach`/`prove` — `prove` corroborates z3+bitwuzla and emits a DRAT cert, checker gated) |
| [`crn-smtlib`](./pairs/crn-smtlib/README.md)   | CRN → SMT-LIB   | schema-determined unrolling | `predicted` | **partial** (uni- + bimolecular + catalysis / multi-product + synthesis / degradation + self-loop + **multiple-reactions** + empty-network: `A -> B`, `A + B -> C`, `2 A -> B`, `A -> 2 B`, `A -> B + C`, `0 -> A`, `A -> 0`, `A -> A`, ≥2 reactions (per-step reaction selection w/ mutual exclusion + nested-`ite` net updates), 0 reactions → `QF_LIA` unroll + z3 + firing-flag witness replay, `smt_model_ok` agrees with replay incl. a multi-reaction schedule using both reactions; 10/10 probed reaction classes, out-of-scope per-reaction *shapes* (molecularity ≥3, `2 A -> 2 B`, `0 -> 0`) still typed `unsupported`) |
| [`riscv-sail`](./pairs/riscv-sail/README.md)   | RISC-V → Sail   | from the RISC-V Sail model | `checked` | **partial** (RV64IMC) |
| [`sail-btor2`](./pairs/sail-btor2/README.md)   | Sail → BTOR2    | Sail → transition system | `checked` → `proved` | **partial** (RV64IMC **plus the AArch64 arm**, translator v0.2 — an `isa=aarch64` Sail object lowers to `aarch64-btor2`'s state space (`pc`/`x0`–`x30`/`sp`/`nzcv`/`m0`–`m63`/`halted`) via the Sail-derived A64 `Expr` trees, completing the second `aarch64 → smtlib` route; the RISC-V arm byte-for-byte unchanged) |
| [`aarch64-sail`](./pairs/aarch64-sail/README.md) | AArch64 → Sail | from the Arm Sail model | `checked` | **partial** (ALU + flag-set + branches + memory + 32-bit W forms: `ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `ADDS`/`CMN`, `B.cond`, `B`/`BL`, `LDR`/`STR`, and their 32-bit W variants; 27/33 probes, Sail interp v0.7; translator v0.2 threads an optional `reg_eq` property into the Sail object, so the composed route decides reachability) |
| [`smiles-formula`](./pairs/smiles-formula/README.md) | SMILES → molecular formula | schema-determined (compile pair) | `predicted` | **partial** (organic-subset graph of single / double / triple bonds — chains, heteroatoms `B C N O P S F Cl Br I`, nested **branches** `(...)`, **double** `=` / **triple** `#` bonds, **ring-closure bonds** (digit `1`-`9` / `%nn`), **and bracket atoms** `[...]` (any element, explicit H; isotope/charge/chirality/class not counted); **14/17** constructs, rest typed `unsupported`; smiles interp `0.6`) |
| [`python-smtlib`](./pairs/python-smtlib/README.md) | Python → SMT-LIB | `QF_LIA` SSA lowering (CPython oracle) | `predicted` / `checked` | **partial** (slice 6: straight-line integer function + **`if`/`else`** + a **bounded loop** `for i in range(<const>)` + a **BMC-bounded loop** `while <cond>` + **nested loops** + **fixed-length integer lists** — assignment + linear arithmetic + an `ite` SSA branch merge + a fully-unrolled `for` + a `while` unrolled to the fixed bound `K` = 8 with a terminated-within-`K` assertion + a loop nested in another loop (within the caps `MAX_LOOP_DEPTH` = 2 / `MAX_UNROLL_PRODUCT` = 64) + a list of static length `L` ≤ `MAX_LIST_LEN` = 16 modeled as a **tuple of `L` `Int`s** — *not* an SMT `Array`, so the encoding stays in `QF_LIA` (list literal, const / dynamic index read & write via an `ite` chain with a `0≤i<L` range constraint, `len`) + a trailing `assert` → `QF_LIA` + z3 + input-assignment witness replayed through pinned CPython down the taken branch / through the (nested) unrolled loops / driving the list to its firing element; **11/27 constructs** covered, up from 6/20 — the five list constructs ratcheted in (`List` leaves the gap; an over-cap / nested list itemized as `list-too-long` / `nested-list`); reuses the shared `QF_LIA` evaluator + solvers unchanged; rest typed `unsupported`) |

## Coverage and status

A pair's status reflects **measured coverage**, not a self-declaration
([`BENCHMARKS.md`](./BENCHMARKS.md)): `registered` → `partial (<coverage>)` →
`built`. `built` requires meeting the brief's coverage target (construct
inventory + public suite) with every unsupported construct hard-aborting.
Route status — branch-agreement and composed coverage per route — is computed
by the merge-triggered **route-grader agent** ([`AGENTS.md`](./AGENTS.md) §7)
and recorded against the routes below.

## Routes

The pairs form two reasoning **hubs** and a bridge between them
([`ROUTES.md`](./ROUTES.md)):

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
  ([`ROUTES.md`](./ROUTES.md) §4–5).
- **Solve-step corroboration.** Every BTOR2-targeting front-end can be
  decided native-vs-bridged through `btor2-smtlib`
  ([`SOLVERS.md`](./SOLVERS.md) §7).
- **Composed coverage** (the route-grader's third measurement; `gurdy
  route-coverage <src> <dst>`). Computed today: `riscv → smtlib` **96/96** (direct)
  and **95/95** (via Sail — now RV64IMC), `aarch64 → smtlib` **27/33 along both
  routes** (direct and via the Arm Sail model — the covered sets coincide exactly
  and every miss is one of the 6 out-of-scope A64 probes, localized to the shared
  decode gate; the Sail route was 0/33 until the `sail-btor2` A64 arm landed),
  and `ebpf → smtlib` **126/126** — every front-end
  construct that a pair lowers survives end-to-end to SMT-LIB, with any gap
  localized to the rejecting hop ([`gurdy/core/grade.py`](./gurdy/core/grade.py)).
- **Branch agreement** (now load-bearing). RISC-V reaches BTOR2 two *independent*
  ways — directly (`riscv-btor2`) and via the Sail-derived model
  (`riscv-sail` → `sail-btor2`); the route-grader decides the same reachability
  question along both `riscv → smtlib` routes and confirms they agree
  (REACHABLE/UNREACHABLE), the fidelity cross-check the design exists for
  ([`ROUTES.md`](./ROUTES.md) §4-5). This now reaches the C head: a property
  about a gcc-compiled C program is decided over both `c → smtlib` routes
  (direct and Sail-mediated) and required to agree. **AArch64 now has the same
  solver-level check**: the same `reg_eq` question (register or `sp`) is decided
  along both `aarch64 → smtlib` routes — `aarch64-btor2` vs `aarch64-sail` →
  `sail-btor2` — and the verdicts agree (reach and unreach, incl. across a
  `SUBS`/`B.NE` loop; `tests/test_sail_btor2_aarch64.py`).

## Adding to the registry

A human registers a new **language** by adding `languages/<name>/README.md`
(formal semantics + interpreter contract; for reasoning targets, the solver
and checker inventories) and a new **pair** by adding
`pairs/<source>-<target>/README.md` (the brief, per [`AGENTS.md`](./AGENTS.md)
§1), then triggering its per-pair agent. Update the tables above in the same
change.
