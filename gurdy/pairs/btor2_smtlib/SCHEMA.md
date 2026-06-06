# `btor2-smtlib` schema — BTOR2 → SMT-LIB bounded model checking

A **transparent** translation between two *reasoning* languages: `in_lang =
btor2`, `out_lang = smtlib`, `tier = transparent`. It symbolically unrolls a
BTOR2 transition system to a bound `k` and emits SMT-LIB (QF_BV, or QF_ABV when
arrays/memory are present) that is **`sat` iff some `bad` is reachable within `k`
steps**. Fully specified here, so the encoding is predictable byte-for-byte.

This is the `BTOR2 ↔ SMT-LIB` bridge — the single edge the two-hub design was
for (`DESIGN_generalized_pairs.md` §7).

## 1. Why it agrees with the native solver

Every BTOR2 operator maps to the *standard* SMT bit-vector / array operator that
a native BTOR2 solver (e.g. `z3-bmc`) also uses. So the bridged verdict and the
native verdict on the same BTOR2 **must agree** — and a disagreement is a
translator bug, in one tool or the other. That makes the same question decided
two ways (native vs bridged) a "many chains, one question" cross-check
(`DESIGN_generalized_pairs.md` §6). The bridge's own tests assert this agreement
against `riscv-btor2`'s native `z3-bmc`.

## 2. Supported operator subset

Mirrors `riscv_btor2.btor2.evaluator` (the concrete BTOR2 interpreter), so it
covers exactly what the RISC-V lowering emits. An unsupported op raises
`BridgeError` (no silent wrong encoding):

- constants `zero one ones constd const consth`;
- arithmetic/logic `add sub mul and or xor not neg`;
- shifts `sll srl sra` → `bvshl bvlshr bvashr`;
- division `udiv urem sdiv srem` → `bvudiv bvurem bvsdiv bvsrem`;
- comparisons `eq neq ult ugt ulte ugte slt sgt slte sgte` → the SMT predicate
  wrapped to a `bv1` result (`(ite pred #b1 #b0)`);
- `ite` (cond is `bv1`), `sext`/`uext` → `(_ sign_extend|zero_extend n)`,
  `slice` → `(_ extract hi lo)`, `concat`;
- arrays `read`/`write` → `select`/`store` (QF_ABV).

## 3. BMC unrolling

For `t ∈ 0..k`, a fresh SMT constant `n<nid>_<t>` is declared for every node;
combinational nodes are defined by `(= n<nid>_t <expr over operands@t>)` in
file (dependency) order; `state` nodes are free except where constrained:

- `init s state value` ⇒ `n<state>_0 = n<value>_0`;
- `next s state value` ⇒ `n<state>_{t+1} = n<value>_t` for `t ∈ 0..k-1`;
- `constraint c` ⇒ `n<c>_t = #b1` for all `t` (an assumption that must hold);
- `bad b` ⇒ the goal: `(or_{t} (= n<b>_t #b1))`.

States without `init` are free at step 0 (symbolic initial state); states
without `next` are free thereafter. With no `bad`, the formula is `(assert
false)` — nothing to reach, so `unreachable`. A `; @btor2-bmc {...}` header
records the bound and state symbols so the lifter can name the witness.

## 4. Solver, lift, determinism, preservation

- **Solver**: the shared generic `z3-smt` backend (`crn_smtlib.backend`) — runs
  the SMT-LIB in z3: `sat → reachable`, `unsat → unreachable`, else `unknown`.
- **Lift**: on `reachable`, the per-step values of the BTOR2 state variables (by
  symbol) from the model.
- **Determinism**: `encode_bmc` is a pure function of `(model, bound)` — fixed
  declaration/clause order; same inputs, identical bytes.
- **Preservation**: keeps the transition relation, bad states, bit-vector and
  array semantics; **discards** behaviour beyond the bound (bounded model
  checking is incomplete for `unreachable` past `k`).
