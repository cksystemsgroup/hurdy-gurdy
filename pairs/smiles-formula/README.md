# Pair — `smiles-formula`  ·  SMILES → molecular formula

*Status: **partial** (the organic-subset tree of single / double / triple bonds
— bare atoms `B C N O P S F Cl Br I` joined by single bonds, **double** `=` and
**triple** `#` bonds, with **branches** `(...)`, and implicit hydrogens; coverage
**9/17**). A compile pair and field-blindness witness; ported from v2, widened to
the organic-subset heteroatoms (SMILES interpreter `0.2`), then to branches
(SMILES interpreter `0.3`), then to double/triple/explicit-single bonds (SMILES
interpreter `0.4`). The full translation schema is in [`SPEC.md`](./SPEC.md);
implementation under
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

## Built — the organic-subset tree of single / double / triple bonds (`partial`, 9/17)

**Covered constructs (end-to-end through the square):** the **organic-subset
tree of single / double / triple bonds** — bare atoms `B C N O P S F Cl Br I`
(alongside the original carbon `C`) joined by implicit single bonds, the
explicit single bond `-` (order 1), **double** bonds `=` (order 2) or **triple**
bonds `#` (order 3), optionally with nested parenthesized **branches** `(...)`,
with implicit hydrogens filled by the pinned per-element valence rule (`B`3 `C`4
`N`3 `O`2 `P`3 `S`2 `F`/`Cl`/`Br`/`I`1; H = `normal_valence − degree`, where
**degree is the sum of bond orders** and counts branch bonds). Chains may **mix
elements**: `C` → `CH4`, `CCO` → `C2H6O` (ethanol). A **branch** `(...)` is a
sub-chain bonded to the atom it follows (its *parent*): `C(C)C` → `C3H8`,
`CC(C)C` → `C4H10` (isobutane), `CC(C)(C)C` → `C5H12` (neopentane). A **bond
token** `= # -` between two atoms sets the order of the bond joining them, and a
double/triple bond lowers the incident atoms' hydrogen count: `C=C` → `C2H4`
(ethene), `C#C` → `C2H2` (ethyne), `C=O` → `CH2O` (formaldehyde), `O=C=O` →
`CO2` (carbon dioxide), `CC#N` → `C2H3N` (acetonitrile), `N#N` → `N2`, `C(=O)O` →
`CH2O2` (formic acid), `CC(=O)C` → `C3H6O` (acetone), `C-C` → `C2H6` (ethane,
explicit single bond ≡ `CC`). The translator `T`, the carry-back `L`, and both
shared interpreters (`gurdy/languages/smiles/`,
`gurdy/languages/molecular_formula/`) share one source of truth — the
molecular-formula language's `parse`/`to_hill` over the same multiset — so the
square commutes by construction.

This is the **bond-order widening** (coverage ratchet,
[`BENCHMARKS.md`](../../BENCHMARKS.md) §5): **6/17 → 9/17**, nothing dropped. It
bumped the **shared SMILES interpreter to `0.4`** (AGENTS.md §3, an additive
parse change that carries a per-bond order; strings with no bond token parse
byte-for-byte as at `0.3`) and the translator to `0.4`. The molecular-formula
language is already element/multiset-general and needed no change; the pair's
`T`/`L`/`π` were unchanged (a double/triple bond only changes which atom multiset
the shared reader produces, by raising incident-atom degree). The earlier
**branch widening** (`5/17 → 6/17`, interp `0.2 → 0.3`) added parenthesized
sub-chains; the **heteroatom widening** (`1/17 → 5/17`, interp `0.1 → 0.2`)
generalized the carbon-only chain to the full organic subset of bare atoms.

**Fidelity: `predicted`.** Evidence: the self-contained schema in
[`SPEC.md`](./SPEC.md) (per-element valence table + the stack-based grammar that
carries a bond order, and the sum-of-orders degree rule) determines the output
bytes (Hill notation gives the canonical, host-independent element order); a
twice-and-diff test (`tests/test_smiles_formula.py`) confirms byte-identical
output for `T` and both interpreters (also verified across `PYTHONHASHSEED`); the
commuting-square oracle aligns `I_s(p) ≡_π L(I_t(T(p)))` on a heteroatom,
branched **and multiply-bonded** corpus.

**Out-of-scope → typed abort** (`unsupported: smiles:<construct>`,
[`BENCHMARKS.md`](../../BENCHMARKS.md) §3). Construct coverage **9/17** of the
spec-enumerable inventory (`coverage.measure` over
`gurdy/pairs/smiles_formula/inventory.py`). In scope: `organic-chain` (the
mixed-element single-bonded chain probe `CCO`), the four heteroatom probes
`organic-atom-N`/`-O`/`-Cl`/`-Br`, `branch` (the parenthesized sub-chain probe
`C(C)C`), and now `double-bond` (`C=C`), `triple-bond` (`C#C`), and
`explicit-single-bond` (`C-C`). A **malformed branch** (unbalanced/empty parens,
`(` with no parent) is itself a typed abort — `unbalanced-branch` /
`branch-without-parent` / `empty-branch`. A **dangling bond** (a `= # -` token
with no atom on one side, `=C`/`C=`/`C==C`/`C=(C)C`) aborts `dangling-bond`, and
a **bond order exceeding an atom's valence** (`F=C`, `O#C`) aborts
`valence-exceeded` — never a silent wrong formula. A still-unsupported construct
does not become reachable just by sitting inside a branch (`C(C$C)C` still aborts
`quadruple-bond`); but a double/triple bond inside a branch *is* now in scope
(`C(=O)O` → `CH2O2`). The `unsupported` histogram (probe count blocked, by the
construct named first under left-to-right parsing; `bracket-atom` subsumes the
charge/isotope/stereo probes that live inside `[...]`):

```
aromatic-atom          1   (c1ccccc1)
bracket-atom           4   ([CH4] [NH4+] [13C] [C@H])
disconnection          1   (C.C)
ring-bond              1   (C1CCCCC1)
stereo-bond            1   (F/C=C/F)
```

**Tests:** `python -m unittest discover -s tests` (full repo suite: 814 tests,
2 host-skips; the 5 `c_riscv` errors are a pre-existing host gcc-toolchain gap,
unrelated — the 47 `test_smiles_formula` tests pass: per-element / per-molecule /
per-branch / per-bond-order vs spec, the sum-of-orders degree rule, the per-bond
`orders` tuple, twice-and-diff on `T` + both interpreters, the commuting-square
check on a heteroatom + branched + multiply-bonded corpus, carry-back replay
through `L`, registration smoke, the dangling-bond / valence-exceeded /
malformed-branch / unsupported-inside-a-branch aborts, and the 9/17
coverage/histogram check with the ratchet asserted not to have dropped anything).

**What we learned (PAIRING.md §9).** The bond-order widening was again **purely
additive in the source-language layer** and touched only
`gurdy/languages/smiles/graph.py` (interp bump `0.3` → `0.4`) plus the inventory;
the pair's `T`/`L`/`π` and the molecular-formula language were unchanged. Three
points worth recording: (1) `bonds` was kept as bare `(i, j)` index pairs and a
**parallel `orders` tuple** added alongside, so single-bond/branch strings emit a
byte-for-byte identical `bonds` list (every order `1`) — the `0.3` behavior is
literally unchanged (asserted in tests), and only the degree computation changed
from "count bonds" to "sum bond orders". (2) The `max(0, V − degree)` clamp from
earlier slices would have **silently** turned an over-bonded atom (`F=C`, a
valence-1 fluorine in a double bond) into a wrong, hydrogen-free formula; the
honest-failure rule (BENCHMARKS.md §3) requires this be a *typed* abort, so we
reject `valence-exceeded` *before* filling hydrogens — making the clamp
unreachable and the rule a plain subtraction. (3) A **bond token is a real
boundary**: a `= # -` with no atom on one side (`=C`, `C=`, `C==C`, before/after
a `(`/`)`) is a `dangling-bond` typed abort, never a silent drop. Bond order is
also discarded by `π` (it only affects implicit-H counts), so `C-C` ≡ `CC` and
`O=C-C` ≡ `O=CC` come out byte-identical — an extra order-independence witness.

**Future widening** (coverage ratchet, [`BENCHMARKS.md`](../../BENCHMARKS.md)
§5): ring closures (digits / `%`), then bracket atoms / charges / isotopes /
aromatic atoms / stereo, and finally a public coverage anchor (RDKit/InChI
canonical formula over a ChEMBL/PubChem slice) as the external oracle.
