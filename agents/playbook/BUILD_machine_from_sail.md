# Playbook — build a BTOR2 machine model from Sail (referential)

You are an autonomous builder on branch `machine/<group>`. Your job is the
opposite of a pair builder: **mirror Sail faithfully** into a BTOR2 machine
model and **prove** the two agree. You HAVE Sail access — use it.

## The artifact

A universal CPU transition system in BTOR2 (`tools/sail_btor2_machine`):
state = (PC, regfile-array, mem-array, CSRs, halted); transition = one
fetch -> decode -> execute -> pc-update step. The program is data in the
initial memory array; per-program "translation" is later just
initialization.

## Loop

1. Take the fixed harness (`tools/sail_btor2_machine/harness.py`) — do not
   reinvent the state/transition shape.
2. For each instruction, transcribe its Sail `execute` clause into a BTOR2
   execute fragment; build the decoder. Record provenance
   `{sail_clause, btor2_fragment}` per instruction (`generate.py`).
3. **Prove equivalence per instruction**: discharge `encode(instr) ==
   sail_relation(instr)` for all inputs (QF_BV). Then the harness lemma
   (fetch/decode/pc/control == Sail `step`). `verify.py`.
4. Subtract implementation-defined points (`semantics/<group>/idf_allowlist.yaml`).
5. When the `MachineFidelityReport` is `green` (all instructions proven,
   harness lemma ok, no un-allowlisted divergence), publish the realization
   and flip `GROUP.yaml`'s `equivalence: GREEN`.

## Scope guidance

Start with the base integer + multiply set (RV64I/M) — small symbolic input
space, cheap decisive lemmas. Memory/CSR/trap and FP come later (Sail is
large and BTOR2 least comfortable there). A clean RV64I/M machine already
unblocks the `riscv_btor2` `machine` path.

## Note — you are also validating Sail

A per-instruction lemma that *cannot* be discharged is a signal: either your
fragment is wrong, or (rarely) Sail is. Minimize the counterexample to a
single instruction + operands, check the manual, and file upstream if Sail
is the suspect (after subtracting IDF).
