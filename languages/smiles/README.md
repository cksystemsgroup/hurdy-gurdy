# Language — SMILES

SMILES (Simplified Molecular-Input Line-Entry System): a line notation for
molecular structure. A second non-CS source language; source of the
`smiles-formula` **compile** pair (a field-blindness witness — the same
machinery carries an entirely non-computational translation).

## Formal semantics (source of truth)

The **OpenSMILES specification** defines a SMILES string's meaning as a
**labeled molecular graph** (atoms with element/charge/isotope/hydrogen
counts; bonds with order; rings via ring-bond numbers; implicit-hydrogen
rules). Canonical references for normalized forms are **RDKit** and the
**InChI** algorithm. The meaning function is total over well-formed SMILES,
which makes downstream translations schema-predictable.

## Formal model — no Sail; the OpenSMILES graph semantics

Not an ISA — no Sail. The OpenSMILES graph semantics is the formal model;
RDKit / InChI canonicalization are the external oracles for the shared
interpreter and the `smiles-formula` translation.

## Shared interpreter

**Role: source.** A deterministic SMILES reader producing the molecular
graph (and its normalized atom multiset). Its "behavior" is the parsed graph
rather than a temporal trace; the projection a pair declares selects which
graph features must be preserved ([`ARCHITECTURE.md`](../../ARCHITECTURE.md)
§5). Validate against RDKit/InChI. Shared by every SMILES pair.

*Status: **partial** — built (`gurdy/languages/smiles/`, interpreter **`0.3`**):
the organic-subset **single-bonded tree** with implicit-hydrogen valence filling
— bare atoms `B C N O P S F Cl Br I` joined by single bonds, with nested
parenthesized **branches** `(...)` (`C`, `CCO`, `CN`, `O`, `CCl`, `C(C)C`,
`CC(C)C`, `C(C)(C)C`, `C(O)C`, …), implicit H = `max(0, normal_valence −
degree)` from the per-element valence table (`B`3 `C`4 `N`3 `O`2 `P`3 `S`2
`F`/`Cl`/`Br`/`I`1; `P` uses the OpenSMILES default 3), where **degree counts
branch bonds**. Every other OpenSMILES construct — rings, multiple/explicit
bonds, aromatic (lowercase) and bracket atoms, charges, isotopes, stereo,
disconnection — hard-aborts `unsupported: smiles:<construct>`
([`BENCHMARKS.md`](../../BENCHMARKS.md) §3); a malformed branch
(unbalanced/empty parens, `(` with no parent) is its own typed abort. Contributed
first by [`smiles-formula`](../../pairs/smiles-formula/README.md).*

**Interpreter versions** (AGENTS.md §3): `0.3` — *additive* widening to
**branches** `(...)` (a stack-based parse: a parenthesized sub-chain bonds its
first atom to the parent atom it follows, then the main chain resumes from the
parent; possibly nested). Still single bonds; an atom's degree now counts its
branch bonds. Branch-free behavior is byte-for-byte identical to `0.2`. `0.2` —
*additive* widening from carbon-only to the full organic subset of bare atoms
(the valence table above), so a single-bonded chain may mix elements;
carbon-chain behavior unchanged. `0.1` — the organic-subset carbon chain
(carbon valence 4).

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): public molecule
sets (**ChEMBL** / **PubChem** subsets, RDKit's test molecules), pinned.
There is no behavioral verdict; coverage is the fraction of molecules whose
formula matches the **RDKit/InChI** canonical reference (the oracle).

## Pairs over this language

- [`smiles-formula`](../../pairs/smiles-formula/README.md) — source.
