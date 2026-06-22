# Pair — `smiles-formula`  ·  SMILES → molecular formula

*Status: **partial** (one construct: the organic-subset carbon chain with
implicit hydrogens). A compile pair and field-blindness witness; ported from
v2. The full translation schema is in [`SPEC.md`](./SPEC.md); implementation
under [`gurdy/pairs/smiles_formula/`](../../gurdy/pairs/smiles_formula/).*

Translate a SMILES string to its molecular formula (Hill notation). This is
a **compile pair**, not a reasoning pair: its target is a representation, not
a solver input, so it has no solver and no `proved` tier — only a faithful,
deterministic re-representation. It exists to show the same pair machinery
and commuting-square contract carry an entirely **non-computational**
translation unchanged.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** SMILES — [`languages/smiles`](../../languages/smiles/README.md).
- **Target.** molecular formula —
  [`languages/molecular-formula`](../../languages/molecular-formula/README.md).
- **Translator `T`.** A schema-determined map: parse the SMILES molecular
  graph, apply implicit-hydrogen rules, count atoms, emit Hill notation.
  Deterministic and **schema-predictable**.
- **Source interpreter.** The **shared** SMILES interpreter (the graph
  reader) ([`languages/smiles`](../../languages/smiles/README.md)) — reused;
  contributed by this pair if first.
- **Target interpreter.** The **shared** molecular-formula reader/normalizer
  ([`languages/molecular-formula`](../../languages/molecular-formula/README.md))
  — reused.
- **Target-to-source interpreter `L`.** Maps a formula's atom multiset back
  to the source-graph observable (the multiset). There is no solver witness
  here; `L` is the trivial re-projection that lets the square be checked.
  Pair-owned.

## Projection `π`

The **atom multiset**. The pair preserves the multiset of atoms; it
**discards** connectivity (bonds, rings, stereochemistry) — an explicit,
honest loss ([`PATHS.md`](../../PATHS.md) §3).

## Fidelity target + evidence

- **`predicted`** — given the SMILES and the OpenSMILES + Hill-notation
  rules, the formula is determined byte-for-byte. A compile pair has no
  `proved` tier (no solver); its assurance is byte-prediction plus the
  square.

## Soundness story

The square commutes by construction: the atom multiset computed from the
source graph (`I_smiles`) equals the multiset of the emitted formula
(`L(I_formula(T(p)))`). Validate the SMILES reader against RDKit/InChI
([`languages/smiles`](../../languages/smiles/README.md),
[`PAIRING.md`](../../PAIRING.md) §6).

## Notes for the implementing agent

- This is the cheapest end-to-end witness that the architecture is
  field-blind — keep it small and exact.
- No solver, no certificate; the deliverable is the translator, the trivial
  `L`, and the declared `π` (atom multiset kept, connectivity discarded).

## Built — the thin slice (`partial`)

**Covered construct (end-to-end through the square):** the **organic-subset
carbon chain with implicit hydrogens** — SMILES `C`, `CC`, `CCC`, … (the
alkane skeleton C_n → C_n H_(2n+2)), implicit H filled by the pinned carbon
valence rule (valence 4; H = 4 − single-bond degree). `C` → `CH4`, `CC` →
`C2H6`, `CCC` → `C3H8`. The translator `T`, the carry-back `L`, and both new
shared interpreters (`gurdy/languages/smiles/`, `gurdy/languages/molecular_formula/`)
share one source of truth — the molecular-formula language's `parse`/`to_hill`
over the same multiset — so the square commutes by construction.

**Fidelity: `predicted`.** Evidence: the self-contained schema in
[`SPEC.md`](./SPEC.md) determines the output bytes (Hill notation gives the
canonical, host-independent element order); a twice-and-diff test
(`tests/test_smiles_formula.py`) confirms byte-identical output for `T` and
both interpreters; the commuting-square oracle aligns `I_s(p) ≡_π L(I_t(T(p)))`
on the corpus.

**Out-of-scope → typed abort** (`unsupported: smiles:<construct>`,
[`BENCHMARKS.md`](../../BENCHMARKS.md) §3). Construct coverage **1/17** of the
spec-enumerable inventory (`gurdy coverage` over `gurdy/pairs/smiles_formula/inventory.py`).
The `unsupported` histogram (probe count blocked, by the construct named first
under left-to-right parsing; bracket-atom subsumes the charge/isotope/stereo
probes that live inside `[...]`):

```
bracket-atom           4   ([CH4] [NH4+] [13C] [C@H])
aromatic-atom          1   (c1ccccc1)
branch                 1   (C(C)C)
disconnection          1   (C.C)
double-bond            1   (C=C)
explicit-single-bond   1   (C-C)
organic-atom:Br        1   (Br)
organic-atom:Cl        1   (Cl)
organic-atom:F         1   (F)
organic-atom:N         1   (N)
organic-atom:O         1   (O)
ring-bond              1   (C1CCCCC1)
triple-bond            1   (C#C)
```

**Tests:** `python -m unittest discover -s tests` (full repo suite: 258 tests,
2 host-skips, OK — includes the 17 `test_smiles_formula` tests:
per-construct/spec, twice-and-diff on `T` + both interpreters, the
commuting-square check, carry-back replay through `L`, registration smoke, and
the coverage/histogram check).

**What we learned (PAIRING.md §9).** The `predicted` compile pair needed *no*
framework change: the same trace/observable contract, oracle, coverage harness,
and registry that serve the reasoning pairs carry an entirely non-computational
translation unchanged — the field-blindness witness the brief promised. The one
subtlety worth recording for the next widening: a left-to-right SMILES parser
names the *outermost* out-of-scope construct first (`[...]` reports
`bracket-atom`, not the charge/isotope/stereo inside it), so widening to bracket
atoms must come before charges/isotopes/stereo can be itemized separately.

**Future widening** (coverage ratchet, [`BENCHMARKS.md`](../../BENCHMARKS.md)
§5): other organic-subset elements (valence table for N/O/P/S/F/Cl/Br/I/B),
branches `()`, ring closures, multiple bonds (bond-order affects implicit H),
then bracket atoms / charges / isotopes / aromatic atoms / stereo, and finally a
public coverage anchor (RDKit/InChI canonical formula over a ChEMBL/PubChem
slice) as the external oracle.
