# Language — Sail

Sail is a language for **describing instruction-set architectures**: an ISA
written in Sail has an executable, formally-specified semantics. Both RISC-V
and Arm have official Sail models, so in the registry Sail is the *mediating*
language of two BTOR2 routes: `riscv-sail` (then `sail-btor2`) re-encodes
RISC-V, and `aarch64-sail` (then `sail-btor2`) re-encodes AArch64 — each a
second, independent path to BTOR2 to **cross-check against the direct
`riscv-btor2` / `aarch64-btor2` route** ([`PATHS.md`](../../PATHS.md) §4–5).

## Formal semantics (source of truth)

The Sail language's formal semantics, instantiated at an **official ISA
model in Sail** — the RISC-V model for `riscv-sail`, the Arm model
(`sail-arm`, from Arm's ASL) for `aarch64-sail`. The meaning of a Sail object
here is the architectural behavior that model defines — by construction the
ISA itself. The value of routing through Sail is that this is a *different
artifact* expressing the *same* ISA than the hand-built `riscv-btor2` /
`aarch64-btor2` translator, so agreement between the two routes is real
corroboration and a disagreement localizes a genuine bug.

A pair states which Sail model and version it pins; the language is the Sail
semantics.

## Shared interpreter

**Role: source and target.** Sail is a *target* of `riscv-sail` and
`aarch64-sail`, and a *source* of `sail-btor2`. One model-agnostic
interpreter serves all three — it executes whichever Sail object (the RISC-V
or the Arm model) a pair supplies.

Contract ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5):

- **Input.** A Sail object (the pinned RISC-V model applied to a program
  image) plus a binding — initial state and a step bound.
- **Behavior.** A trace of **post-step** states of the Sail model's
  architectural state.
- **Observables.** The architectural state the model exposes — chosen so
  that it projects onto the *same* observable space as the matching ISA
  interpreter ([`languages/riscv`](../riscv/README.md),
  [`languages/aarch64`](../aarch64/README.md)), because the point of a Sail
  route is to compare against the direct route at BTOR2. Keeping projections
  compatible across the two routes is a shared obligation of `riscv-sail` /
  `riscv-btor2` and `aarch64-sail` / `aarch64-btor2`.
- **Determinism.** Pure; pinned model + program + binding → identical trace.

The Sail model is large; an agent may build this interpreter by **driving
the Sail-generated executable model** rather than re-implementing it, as
long as the result is deterministic and exposes the observable conventions
above ([`PAIRING.md`](../../PAIRING.md) §9 open question on large
interpreters).

*Status: **partial** — an independent **RV64IMC** interpreter is built
(`gurdy/languages/sail/`, tests in `tests/test_sail_btor2_pair.py` /
`tests/test_sail_expr.py`): the base integer set (ALU, control flow,
loads/stores), the M extension, and the **C (compressed) extension** — an
*independent* RV64C decompressor (`compressed.py`, cross-checked against the
RISC-V one on the fixed encoding) expands 16-bit instructions to their base form,
and the fetch handles the true 2-byte-granular PCs (`tests/test_sail_compressed.py`).
Each instruction's computational content is
a Sail-derived `Expr` tree that lowers identically to a concrete evaluator, to
BTOR2 (the `sail-btor2` datapath), and to z3 (the equivalence check) — so the
encoding cannot drift and is independent of the hand-written `riscv`
interpreter. It is wired to the gold oracle: `sail.differential.sail_subject`
feeds the shared harness so the Sail interpreter is validated against the real
`sail_riscv_sim` (`tests/test_sail_differential.py`, gated on the pinned
binary), and hermetically it produces the same executed stream as the
hand-written RISC-V interpreter on RV64IMC (full-trace differential on a
compressed program). The interpreter is now **model-agnostic at the dispatch**:
a Sail object tagged `isa=aarch64` runs an **additive AArch64 arm**
(`aarch64.py`, interp v0.4 — the RISC-V path is byte-for-byte unchanged) for the
`aarch64-sail` route, covering the ALU family `ADD`/`SUB` (immediate) + `MOVZ`
**plus** the first NZCV write (`SUBS`/`CMP` immediate) and the first conditional
control flow (`B.cond`) (all 64-bit) and evaluating the same Sail-derived `Expr`
vocabulary over A64's `x0`–`x30`/`sp`/`nzcv` state — the `SUBS`/`CMP` flag pack
(`N`/`Z`/`C`/`V`) and the `B.cond` condition predicate are themselves `Expr` trees
(`tests/test_aarch64_sail_pair.py`). The v0.2 → v0.3 bump added `SUB`/`MOVZ`; the
v0.3 → v0.4 bump adds `SUBS`/`CMP` + `B.cond`, mirroring the `aarch64-btor2` `0.3`
widening so the two AArch64→BTOR2 routes decide the same constructs again (their
covered sets coincide exactly). Auto-deriving the `Expr` trees from the Sail
source, widening the A64 arm beyond this family, and the official `sail-arm`
differential are the named pending increments.*

## Pairs over this language

- [`riscv-sail`](../../pairs/riscv-sail/README.md) — target.
- [`aarch64-sail`](../../pairs/aarch64-sail/README.md) — target.
- [`sail-btor2`](../../pairs/sail-btor2/README.md) — source.
