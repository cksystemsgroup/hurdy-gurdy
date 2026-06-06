# `smiles-formula` schema — SMILES → Hill molecular formula

A **transparent compile pair** (`DESIGN_pair_taxonomy.md`): `in_lang = smiles`,
`out_lang = molecular-formula`, `tier = transparent`. The translation is pure,
deterministic, and fully specified here — anyone who has read this schema can
predict the output formula for any in-subset SMILES, byte-for-byte
(`PAIRING.md` §5, the LLM-predictability invariant, in chemistry).

This is the project's first non-CS, non-programming input language: SMILES is a
chemistry line notation whose formal semantics is a molecular graph. It is also
the second registered pair — the field-blindness witness `PAIRING.md` §15 asks
for before any abstraction earned on `riscv-btor2` is generalized further.

## 1. Supported subset

Anything outside this subset raises `SmilesError` (the hop never guesses).

- **Atoms** (organic subset, no brackets): `B C N O P S F Cl Br I`. Two-letter
  symbols `Cl`/`Br` are matched before one-letter ones.
- **Bonds**: `-` single, `=` double, `#` triple. A bond between two adjacent
  atoms with no symbol is single.
- **Branches**: `(` … `)`, nestable.
- **Ring closures**: single digits `1`–`9`. The bond order of a ring closure
  may be written at either end (`C=1…1` or `C1…=1`); if written at both, they
  must agree.

Explicitly **rejected** (out of subset): bracket atoms `[...]` (hence charges,
isotopes, explicit-H counts, stereo parity), aromatic lowercase atoms
(`c n o …`), the disconnected-structure dot `.`, two-digit ring bonds `%nn`,
and any other character.

## 2. Implicit hydrogens

For each atom, let *b* be the sum of the bond orders of its bonds (chain,
branch, and ring-closure bonds; **not** counting hydrogens). The implicit
hydrogen count is

> `H = v − b`, where `v` is the **smallest standard valence ≥ b**;
> `H = 0` if `b` exceeds the largest standard valence (no validity check).

Standard valences:

| Element | Valences |
|---|---|
| B | 3 |
| C | 4 |
| N | 3, 5 |
| O | 2 |
| P | 3, 5 |
| S | 2, 4, 6 |
| F, Cl, Br, I | 1 |

Examples: `C` → CH4 (b=0, v=4); a chain `-CH2-` carbon has b=2 → 2 H; a triple
-bonded nitrile N (`C#N`) has b=3 → 0 H; sulfone sulfur (`S(=O)(=O)`) has b=6
→ 0 H.

## 3. Output: Hill notation

Tally each element across all atoms, add total implicit H, then order:

- **with carbon present**: `C`, then `H`, then every other element
  alphabetically;
- **with no carbon**: every element (including `H`) alphabetically.

A count of 1 is written implicitly (`CO2`, not `C1O2`).

Worked: `CCO` → C 2, H 6, O 1 → **`C2H6O`**. `CC(=O)O` → **`C2H4O2`**.
`O=C=O` → **`CO2`**. `C1CCCCC1` → **`C6H12`**. `N` → **`H3N`** (no carbon →
alphabetical). `CS(=O)(=O)C` → **`C2H6O2S`**.

## 4. Determinism

`smiles_to_formula` is a pure function of the input string: same SMILES →
identical formula, no global state, no iteration-order dependence (counts are
tallied into a dict and emitted in the fixed Hill order). The chain-level
`recompile_and_diff` (`gurdy/core/chain.py`) therefore reports it deterministic.

## 5. Preservation contract (informal)

This hop **keeps** the atom multiset (elements + counts, including derived
hydrogens) and **discards** connectivity, bond orders, rings, stereochemistry,
and charge. It is a deliberately lossy view — which makes it the natural first
example for a formal `preservation` contract (`DESIGN_pair_taxonomy.md` §8,
deferred at Stage 4 until a second field existed; that field is now this one).
The loss is intrinsic to "molecular formula," not an implementation gap.
