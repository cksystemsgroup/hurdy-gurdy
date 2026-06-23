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

*Status: **partial** — built (`gurdy/languages/smiles/`, interpreter **`0.5`**):
the organic-subset **graph of single / double / triple bonds — chains, branches,
and rings** with implicit-hydrogen valence filling — bare atoms `B C N O P S F Cl
Br I` joined by single bonds, the explicit single bond `-`, **double** bonds `=`
(order 2) or **triple** bonds `#` (order 3), with nested parenthesized
**branches** `(...)` and **ring-closure bonds** (a digit `1`-`9` or `%nn` label)
(`C`, `CCO`, `O`, `CCl`, `C(C)C`, `CC(C)C`, `C=C`, `C#C`, `C=O`, `O=C=O`, `CC#N`,
`C(=O)O`, `C1CCCCC1`, `C1CC1`, `C1=CCCCC1`, `O1CCOCC1`, …), implicit H =
`normal_valence − degree` from the per-element valence table (`B`3 `C`4 `N`3 `O`2
`P`3 `S`2 `F`/`Cl`/`Br`/`I`1; `P` uses the OpenSMILES default 3), where **degree
is the sum of bond orders** (and counts branch *and ring* bonds). Every other
OpenSMILES construct — the quadruple/aromatic bonds, aromatic (lowercase) and
bracket atoms, charges, isotopes, stereo, disconnection — hard-aborts
`unsupported: smiles:<construct>` ([`BENCHMARKS.md`](../../BENCHMARKS.md) §3); a
malformed branch (unbalanced/empty parens, `(` with no parent), a dangling bond
token (no atom on one side), a malformed ring closure (unclosed label, no left
atom, self-ring, mismatched ring-bond orders, `%` not followed by two digits),
and a bond order exceeding an atom's valence are each their own typed abort.
Contributed first by [`smiles-formula`](../../pairs/smiles-formula/README.md).*

**Interpreter versions** (AGENTS.md §3): `0.5` — *additive* widening to
**ring-closure bonds**: a digit `1`-`9` or two-digit `%nn` label after an atom
marks a ring-bond endpoint, and the second occurrence of the same label closes
the ring by bonding the two endpoint atoms (the bond counting toward both their
degrees; its order is 1, or the order of a bond token written immediately before
the label, `C=1…C1`). The implicit-H rule `normal_valence − Σ bond_orders` is
unchanged (`C1CCCCC1` → `C6H12`, `C1CC1` → `C3H6`, `C1=CCCCC1` → `C6H10`,
`O1CCOCC1` → `C4H8O2`). Behavior on any string with no ring label is
byte-for-byte identical to `0.4`. A malformed ring closure (`ring-bond-unclosed`,
`ring-bond-no-atom`, `ring-bond-self`, `ring-bond-order-mismatch`,
`ring-bond-malformed`) and a ring bond exceeding an atom's valence
(`valence-exceeded`) are typed aborts. `0.4` — *additive* widening to
**double** `=` (order 2) and **triple** `#` (order 3) bonds, plus the explicit
**single** bond `-` (order 1). A bond token between two atoms sets the order of
the bond joining them; an atom's degree is now the *sum of its bond orders*, and
implicit H = `normal_valence − Σ bond_orders` (`C=C` → `C2H4`, `C#C` → `C2H2`,
`C=O` → `CH2O`, `O=C=O` → `CO2`). Behavior on any string with no bond token is
byte-for-byte identical to `0.3` (every bond order is `1`). A dangling bond
(`dangling-bond`) and a valence-exceeding bond (`valence-exceeded`) are typed
aborts. `0.3` — *additive* widening to **branches** `(...)` (a stack-based parse:
a parenthesized sub-chain bonds its first atom to the parent atom it follows,
then the main chain resumes from the parent; possibly nested). Branch-free
behavior is byte-for-byte identical to `0.2`. `0.2` — *additive* widening from
carbon-only to the full organic subset of bare atoms (the valence table above),
so a single-bonded chain may mix elements; carbon-chain behavior unchanged.
`0.1` — the organic-subset carbon chain (carbon valence 4).

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): public molecule
sets (**ChEMBL** / **PubChem** subsets, RDKit's test molecules), pinned.
There is no behavioral verdict; coverage is the fraction of molecules whose
formula matches the **RDKit/InChI** canonical reference (the oracle).

## Pairs over this language

- [`smiles-formula`](../../pairs/smiles-formula/README.md) — source.
