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

## Pairs over this language

- [`smiles-formula`](../../pairs/smiles-formula/README.md) — source.
