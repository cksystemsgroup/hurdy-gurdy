# Language — molecular formula

A molecular formula: the multiset of atoms in a molecule, written in **Hill
notation** (carbon first, then hydrogen, then other elements alphabetically,
with counts). The **target** of the `smiles-formula` compile pair — a
representation, not a reasoning language (no solver consumes it).

## Formal semantics (source of truth)

The meaning of a molecular formula is an **atom multiset** (element → count).
Hill notation fixes a canonical written form. The reference is IUPAC Hill
notation; equality of formulas is equality of multisets.

## Formal model

None beyond the multiset semantics above — it is a simple, total, canonical
form. No Sail and none needed.

## Shared interpreter

**Role: target.** A deterministic reader/normalizer: parse a formula to its
atom multiset and re-emit canonical Hill notation
([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5). This is the `I_t` the
`smiles-formula` pair's square is checked against. Shared by any pair
targeting molecular formulas.

*Status: **built** — `gurdy/languages/molecular_formula/`: `parse` (flat
Hill-notation string → atom multiset) and `to_hill` (multiset → canonical Hill
string, host-independent element order), with the one-state `Trace` observable
(`atoms`, `formula`). Nested/charged formulas hard-abort `unsupported`.
Contributed first by [`smiles-formula`](../../pairs/smiles-formula/README.md).*

## Pairs over this language

- [`smiles-formula`](../../pairs/smiles-formula/README.md) — target.
