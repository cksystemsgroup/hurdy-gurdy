# Pair — `smiles-formula`  ·  SMILES → molecular formula

*Status: **partial** (the organic-subset single-bonded tree — bare atoms
`B C N O P S F Cl Br I` joined by single bonds, with **branches** `(...)`, and
implicit hydrogens; coverage **6/17**). A compile pair and field-blindness
witness; ported from v2, widened to the organic-subset heteroatoms (SMILES
interpreter `0.2`) and then to branches (SMILES interpreter `0.3`). The full
translation schema is in [`SPEC.md`](./SPEC.md); implementation under
[`gurdy/pairs/smiles_formula/`](../../gurdy/pairs/smiles_formula/).*

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

## Built — the organic-subset single-bonded tree (`partial`, 6/17)

**Covered constructs (end-to-end through the square):** the **organic-subset
single-bonded tree** — bare atoms `B C N O P S F Cl Br I` (alongside the
original carbon `C`) joined by implicit single bonds, optionally with nested
parenthesized **branches** `(...)`, with implicit hydrogens filled by the pinned
per-element valence rule (`B`3 `C`4 `N`3 `O`2 `P`3 `S`2 `F`/`Cl`/`Br`/`I`1;
H = `max(0, normal_valence − degree)`, where **degree now counts branch bonds**).
Chains may **mix elements**: `C` → `CH4`, `CCO` → `C2H6O` (ethanol), `CN` →
`CH5N`, `CCl` → `CH3Cl`, `O` → `H2O`, `N` → `H3N`. A **branch** `(...)` is a
sub-chain bonded to the atom it follows (its *parent*), after which the main
chain resumes from that same parent: `C(C)C` → `C3H8` (propane), `CC(C)C` →
`C4H10` (isobutane), `C(C)(C)C` → `C4H10`, `CC(C)(C)C` → `C5H12` (neopentane),
`C(O)C` → `C2H6O` (dimethyl ether), `N(C)C` → `C2H7N`, `C(C(C)C)C` → `C5H12`
(nested). The translator `T`, the carry-back `L`, and both shared interpreters
(`gurdy/languages/smiles/`, `gurdy/languages/molecular_formula/`) share one
source of truth — the molecular-formula language's `parse`/`to_hill` over the
same multiset — so the square commutes by construction.

This is the **branch widening** (coverage ratchet,
[`BENCHMARKS.md`](../../BENCHMARKS.md) §5): **5/17 → 6/17**, nothing dropped. It
bumped the **shared SMILES interpreter to `0.3`** (AGENTS.md §3, an additive
parse change from a linear chain to a stack-based tree parse; branch-free chains
parse byte-for-byte as at `0.2`) and the translator to `0.3`. The
molecular-formula language is already element/multiset-general and needed no
change; the pair's `T`/`L`/`π` were unchanged (a branch only changes which atom
multiset the shared reader produces). The earlier **heteroatom widening**
(`1/17 → 5/17`, interp `0.1 → 0.2`) generalized the carbon-only chain to the
full organic subset of bare atoms.

**Fidelity: `predicted`.** Evidence: the self-contained schema in
[`SPEC.md`](./SPEC.md) (per-element valence table + the stack-based branch
grammar and its degree rule) determines the output bytes (Hill notation gives
the canonical, host-independent element order); a twice-and-diff test
(`tests/test_smiles_formula.py`) confirms byte-identical output for `T` and both
interpreters (also verified across `PYTHONHASHSEED`); the commuting-square oracle
aligns `I_s(p) ≡_π L(I_t(T(p)))` on a heteroatom **and branched** corpus.

**Out-of-scope → typed abort** (`unsupported: smiles:<construct>`,
[`BENCHMARKS.md`](../../BENCHMARKS.md) §3). Construct coverage **6/17** of the
spec-enumerable inventory (`coverage.measure` over
`gurdy/pairs/smiles_formula/inventory.py`). In scope: `organic-chain` (the
mixed-element single-bonded chain probe `CCO`), the four heteroatom probes
`organic-atom-N`/`-O`/`-Cl`/`-Br`, and `branch` (the parenthesized sub-chain
probe `C(C)C`, covered now). A **malformed branch** (unbalanced/empty parens, `(`
with no parent) is itself a typed abort — `unbalanced-branch` /
`branch-without-parent` / `empty-branch` — never a silent wrong formula; and a
still-unsupported construct does not become reachable just by sitting inside a
branch (`C(=O)C` still aborts `double-bond`). The `unsupported` histogram (probe
count blocked, by the construct named first under left-to-right parsing;
`bracket-atom` subsumes the charge/isotope/stereo probes that live inside
`[...]`):

```
aromatic-atom          1   (c1ccccc1)
bracket-atom           4   ([CH4] [NH4+] [13C] [C@H])
disconnection          1   (C.C)
double-bond            1   (C=C)
explicit-single-bond   1   (C-C)
ring-bond              1   (C1CCCCC1)
stereo-bond            1   (F/C=C/F)
triple-bond            1   (C#C)
```

**Tests:** `python -m unittest discover -s tests` (full repo suite: 680 tests,
2 host-skips, OK — includes the 36 `test_smiles_formula` tests:
per-element/per-molecule/per-branch vs spec, the branch degree/connectivity
rule, twice-and-diff on `T` + both interpreters, the commuting-square check on a
heteroatom + branched corpus, carry-back replay through `L`, registration smoke,
the malformed-branch and unsupported-inside-a-branch aborts, and the 6/17
coverage/histogram check with the ratchet asserted not to have dropped anything).

**What we learned (PAIRING.md §9).** The branch widening was again **purely
additive in the source-language layer** and touched only
`gurdy/languages/smiles/graph.py` (interp bump `0.2` → `0.3`) plus the inventory;
the pair's `T`/`L`/`π` and the molecular-formula language were unchanged. Three
points worth recording: (1) Because the valence rule was *already* phrased as
`max(0, V − degree)` over a `bonds` list, branches needed **no change to the
hydrogen-filling code at all** — only the parser had to build the right bonds.
The linear loop became a stack parse where `(` pushes the current parent and `)`
restores it; branch-free strings walk the stack trivially and emit the identical
bond list, so `0.2` behavior is byte-for-byte preserved (asserted in tests). (2)
The same shape of multiset can be written many ways — `C(CC)C`, `CC(C)C`, `CCCC`
all give `C4H10` — and all are byte-identical out, because `π` is the multiset
and connectivity is discarded; the branched/straight spellings are an extra
order-independence witness. (3) **Malformed branches are a real boundary** the
honest-failure rule (BENCHMARKS.md §3) requires we name: an unbalanced `(`/`)`,
a `(` with no parent atom, or an empty `()` each get a *distinct* typed
`unsupported` construct rather than a generic parse error or — worse — a silent
wrong formula. We also confirmed an out-of-scope construct inside a branch still
aborts at that construct (the branch does not "launder" it into scope).

**Future widening** (coverage ratchet, [`BENCHMARKS.md`](../../BENCHMARKS.md)
§5): ring closures, multiple/explicit bonds (bond-order affects implicit H),
then bracket atoms / charges / isotopes / aromatic atoms / stereo, and finally a
public coverage anchor (RDKit/InChI canonical formula over a ChEMBL/PubChem
slice) as the external oracle.
