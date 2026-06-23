# Pair — `smiles-formula`  ·  SMILES → molecular formula

*Status: **partial** (the organic-subset graph of single / double / triple bonds
— bare atoms `B C N O P S F Cl Br I` joined by single bonds, **double** `=` and
**triple** `#` bonds, with **branches** `(...)` and **ring-closure bonds** (a
digit `1`-`9` or `%nn` label), and implicit hydrogens; coverage **10/17**). A
compile pair and field-blindness witness; ported from v2, widened to the
organic-subset heteroatoms (SMILES interpreter `0.2`), then to branches (SMILES
interpreter `0.3`), then to double/triple/explicit-single bonds (SMILES
interpreter `0.4`), then to rings (SMILES interpreter `0.5`). The full
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

## Built — the organic-subset graph of single / double / triple bonds, chains, branches, rings (`partial`, 10/17)

**Covered constructs (end-to-end through the square):** the **organic-subset
graph of single / double / triple bonds — chains, branches, and rings** — bare
atoms `B C N O P S F Cl Br I` (alongside the original carbon `C`) joined by
implicit single bonds, the explicit single bond `-` (order 1), **double** bonds
`=` (order 2) or **triple** bonds `#` (order 3), optionally with nested
parenthesized **branches** `(...)` and **ring-closure bonds** (a digit `1`-`9` or
two-digit `%nn` label), with implicit hydrogens filled by the pinned per-element
valence rule (`B`3 `C`4 `N`3 `O`2 `P`3 `S`2 `F`/`Cl`/`Br`/`I`1; H =
`normal_valence − degree`, where **degree is the sum of bond orders** and counts
chain, branch, *and ring* bonds). Chains may **mix elements**: `C` → `CH4`, `CCO`
→ `C2H6O` (ethanol). A **branch** `(...)` is a sub-chain bonded to the atom it
follows (its *parent*): `C(C)C` → `C3H8`, `CC(C)C` → `C4H10` (isobutane). A
**bond token** `= # -` between two atoms sets the order of the bond joining them:
`C=C` → `C2H4` (ethene), `C#C` → `C2H2` (ethyne), `O=C=O` → `CO2`. A **ring-
closure bond** (a digit `1`-`9` or `%nn` label after an atom; the second
occurrence of the same label closes the ring) bonds the two endpoint atoms, the
bond counting toward both their degrees: `C1CCCCC1` → `C6H12` (cyclohexane),
`C1CC1` → `C3H6` (cyclopropane), `C1=CCCCC1` → `C6H10` (cyclohexene), `O1CCOCC1`
→ `C4H8O2` (1,4-dioxane), `N1CCCCC1` → `C5H11N` (piperidine), `C1CCC2CCCCC2C1` →
`C10H18` (decalin, fused), `C%10CCCCC%10` → `C6H12` (two-digit label). The ring
bond's order is `1` by default, or the order of a bond token written immediately
before the ring digit (`C=1…C1`). The translator `T`, the carry-back `L`, and
both shared interpreters (`gurdy/languages/smiles/`,
`gurdy/languages/molecular_formula/`) share one source of truth — the
molecular-formula language's `parse`/`to_hill` over the same multiset — so the
square commutes by construction.

This is the **ring widening** (coverage ratchet,
[`BENCHMARKS.md`](../../BENCHMARKS.md) §5): **9/17 → 10/17**, nothing dropped. It
bumped the **shared SMILES interpreter to `0.5`** (AGENTS.md §3, an additive
parse change that tracks open ring-closure labels and closes them into a bond;
strings with no ring label parse byte-for-byte as at `0.4`) and the translator to
`0.5`. The molecular-formula language is already element/multiset-general and
needed no change; the pair's `T`/`L`/`π` were unchanged (a ring bond only changes
which atom multiset the shared reader produces, by raising its two endpoints'
degree). The earlier **bond-order widening** (`6/17 → 9/17`, interp `0.3 → 0.4`)
added double/triple/explicit-single bonds; the **branch widening** (`5/17 →
6/17`, interp `0.2 → 0.3`) added parenthesized sub-chains; the **heteroatom
widening** (`1/17 → 5/17`, interp `0.1 → 0.2`) generalized the carbon-only chain
to the full organic subset of bare atoms.

**Fidelity: `predicted`.** Evidence: the self-contained schema in
[`SPEC.md`](./SPEC.md) (per-element valence table + the stack-based grammar that
carries a bond order and tracks ring-closure labels, and the sum-of-orders degree
rule) determines the output bytes (Hill notation gives the canonical,
host-independent element order); a twice-and-diff test
(`tests/test_smiles_formula.py`) confirms byte-identical output for `T` and both
interpreters (also verified across `PYTHONHASHSEED`); the commuting-square oracle
aligns `I_s(p) ≡_π L(I_t(T(p)))` on a heteroatom, branched, multiply-bonded **and
ring** corpus.

**Out-of-scope → typed abort** (`unsupported: smiles:<construct>`,
[`BENCHMARKS.md`](../../BENCHMARKS.md) §3). Construct coverage **10/17** of the
spec-enumerable inventory (`coverage.measure` over
`gurdy/pairs/smiles_formula/inventory.py`). In scope: `organic-chain` (the
mixed-element single-bonded chain probe `CCO`), the four heteroatom probes
`organic-atom-N`/`-O`/`-Cl`/`-Br`, `branch` (the parenthesized sub-chain probe
`C(C)C`), `double-bond` (`C=C`), `triple-bond` (`C#C`), `explicit-single-bond`
(`C-C`), and now `ring-bond` (`C1CCCCC1`). A **malformed branch**
(unbalanced/empty parens, `(` with no parent) is itself a typed abort —
`unbalanced-branch` / `branch-without-parent` / `empty-branch`. A **dangling
bond** (a `= # -` token with no atom on one side) aborts `dangling-bond`. A
**malformed ring closure** — an unclosed label (`C1CC`), a ring digit with no
left atom (`1CCC1`), a self-ring (`C11`), mismatched ring-bond orders
(`C=1CCCCC#1`), or a `%` not followed by two digits (`C%1CC`) — aborts
`ring-bond-unclosed` / `ring-bond-no-atom` / `ring-bond-self` /
`ring-bond-order-mismatch` / `ring-bond-malformed`. A **bond order exceeding an
atom's valence** (`F=C`, `O#C`, or a ring bond that over-bonds an atom, `F1CC1`)
aborts `valence-exceeded` — never a silent wrong formula. A still-unsupported
construct does not become reachable just by sitting inside a branch (`C(C$C)C`
still aborts `quadruple-bond`); but a ring (or double/triple bond) inside a branch
*is* now in scope (`C(C1CC1)C` → `C5H10`). The `unsupported` histogram (probe
count blocked, by the construct named first under left-to-right parsing;
`bracket-atom` subsumes the charge/isotope/stereo probes that live inside
`[...]`):

```
aromatic-atom          1   (c1ccccc1)
bracket-atom           4   ([CH4] [NH4+] [13C] [C@H])
disconnection          1   (C.C)
stereo-bond            1   (F/C=C/F)
```

**Tests:** `python -m unittest discover -s tests` (full repo suite: 961 tests,
2 host-skips; the 5 `c_riscv` errors are a pre-existing host gcc-toolchain gap,
unrelated — the 61 `test_smiles_formula` tests pass: per-element / per-molecule /
per-branch / per-bond-order / per-ring vs spec, the sum-of-orders degree rule
counting ring bonds, the per-bond `orders` tuple including the ring bond,
twice-and-diff on `T` + both interpreters, the commuting-square check on a
heteroatom + branched + multiply-bonded + ring corpus, carry-back replay through
`L`, registration smoke, the dangling-bond / valence-exceeded / malformed-branch /
malformed-ring / unsupported-inside-a-branch aborts, and the 10/17
coverage/histogram check with the ratchet asserted not to have dropped anything).

**What we learned (PAIRING.md §9).** The ring widening was again **purely
additive in the source-language layer** and touched only
`gurdy/languages/smiles/graph.py` (interp bump `0.4` → `0.5`) plus the inventory;
the pair's `T`/`L`/`π` and the molecular-formula language were unchanged. Three
points worth recording: (1) A ring bond is just **one more entry** in the same
`(i, j)` / `orders` lists the chain and branch bonds already use, so the existing
degree computation and `valence-exceeded` guard cover it for free — `F1CC1`
(a valence-1 fluorine in a ring) aborts `valence-exceeded` with no new code, and
the multiset/Hill carry-back is unchanged. (2) **Ring labels are state, and state
must be cleaned up honestly**: an `open_rings` label opened but never closed is a
*latent silent bug* (the ring just vanishes), so end-of-parse asserts
`open_rings` is empty (`ring-bond-unclosed`), reported by the opening **offset**
(a host-independent order, not dict-iteration order) for determinism. (3) The
ring bond order can be written at **either end** (`C=1…C1` or `C1…C=1`), so the
two ends are *reconciled*, not silently last-wins — a `C=1…C#1` mismatch is a
typed abort. Connectivity (and so the ring itself) is discarded by `π`, so
`C1CCCCC1` and a hypothetical open `C6H12` isomer would project equal — the pair
honestly preserves only the **multiset**, exactly as the brief's `π` declares.

**Future widening** (coverage ratchet, [`BENCHMARKS.md`](../../BENCHMARKS.md)
§5): bracket atoms / charges / isotopes / aromatic atoms / stereo, and finally a
public coverage anchor (RDKit/InChI canonical formula over a ChEMBL/PubChem slice)
as the external oracle.
