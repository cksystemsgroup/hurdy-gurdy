# Translation specification — `smiles-formula` (organic-subset tree, single / double / triple bonds)

This is the self-contained, reviewable specification the `predicted` fidelity
claim rests on (PAIRING.md §2, §4). Anyone with the SMILES string and this
document can reproduce the translator's output **byte-for-byte**.

## Scope (this slice)

In scope: a non-empty SMILES string that is a **tree of organic-subset bare
atoms joined by single / double / triple bonds** and nothing else — a run of the
organic-subset element symbols `B C N O P S F Cl Br I` written outside brackets,
joined by **single** bonds (implicit, or the explicit single bond `-`),
**double** bonds `=` (order 2), or **triple** bonds `#` (order 3), optionally
with parenthesized **branches** `(...)` (possibly nested). Examples: `C`, `CC`,
`CCC`, … (alkane skeletons); the heteroatom-mixing chains `CCO` (ethanol), `CN`,
`CF`, `CCl`, `O`, `N`, `NCO`; the branched skeletons `C(C)C`, `CC(C)C`
(isobutane), `C(C)(C)C`, `CC(C)(C)C` (neopentane), `C(O)C` (dimethyl ether),
`N(C)C`, `C(C(C)C)C` …; and the multiply-bonded molecules `C=C` (ethene), `C#C`
(ethyne), `C=O` (formaldehyde), `O=C=O` (carbon dioxide), `CC#N` (acetonitrile),
`N#N`, `C(=O)O` (formic acid), `CC(=O)C` (acetone), `C=CC=C` (1,3-butadiene),
`C-C` (ethane, explicit single bond) … .

Every other OpenSMILES construct is **out of scope** and MUST hard-abort with
`unsupported: smiles:<construct>` (no silent drop). The named out-of-scope
constructs are: ring-bond digits, ring-closure `%`, the quadruple/aromatic bonds
(`$ :`), stereo bonds `/ \`, bracket atoms `[...]`, charges `+`, stereo `@`,
disconnection `.`, and aromatic (lowercase) atoms (`c n o s p b`, …). An
uppercase symbol outside the organic subset aborts as `organic-atom:<symbol>`.
A **malformed branch** — an unbalanced parenthesis (`C(`, `C)`, `C(C))`), a
`(` with no parent atom (`(C)C`, `()`), or an empty branch (`C()C`) — is itself
a typed abort (`unbalanced-branch` / `branch-without-parent` / `empty-branch`).
A **dangling bond** — a bond token `- = #` with no atom on one side (`=C`, `C=`,
`C==C`, `C=(C)C`, `C=)`) — is a typed abort (`dangling-bond`). A **bond order
exceeding an atom's normal valence** (`F=C` — fluorine valence 1; `O#C` — oxygen
valence 2) is a typed abort (`valence-exceeded`), **never** a silently
clamped-to-zero (wrong) formula.

## The schema (deterministic, no adaptive choice)

1. **Parse / tokenize (stack-based, carrying a bond order).** Read the string
   left to right. At each position, the longest organic-subset symbol is one
   atom: the two-letter halogens `Cl` and `Br` are recognized as single atoms (a
   `C` immediately followed by `l` is chlorine, a `B` immediately followed by `r`
   is bromine — *not* carbon+`l` or boron+`r`); every other `B C N O P S F I` is
   a one-letter atom. The parse maintains a single **parent** index `prev` — the
   atom the next atom will bond to (`None` before the first atom) — a **pending
   bond order** (`1` by default; set to `2` by a `=` token, `3` by `#`, `1` by an
   explicit `-`), and a **stack**:

   - An **atom** is appended; if `prev` is not `None`, a bond `(prev, idx)` is
     added with the pending order (always `prev < idx`, since indices only grow),
     and the pending order resets to `1`; then `prev` is set to this new atom.
   - A **bond token** `- = #` sets the pending order for the *next* bond. It must
     sit **between two atoms**: a token with no atom on its left (string start,
     or just after `(`), two tokens in a row, or a token with no atom on its
     right (before `(`/`)` or at end-of-string) is a `dangling-bond`.
   - `(` **opens a branch**: it pushes the current `prev` (which must not be
     `None` — a `(` with no parent atom is `branch-without-parent`) onto the
     stack. The branch's atoms bond off that same parent, with whatever pending
     bond order is open (so `C(=O)O` makes the branch's first bond double).
   - `)` **closes a branch**: it pops the stack (which must be non-empty — an
     unmatched `)` is `unbalanced-branch`) and restores `prev` to the saved
     parent, so the **main chain resumes from the parent**. A branch that
     consumed no atom is `empty-branch`.

   At end-of-string the stack must be empty (an unclosed `(` is
   `unbalanced-branch`) and no bond token may be open (a trailing `=`/`#`/`-` is
   `dangling-bond`). On any string **with no bond token** this is **byte-for-byte
   the old linear/branch behavior**: `prev` walks `0, 1, 2, …`, every bond order
   is `1`, and the bonds come out `(0,1), (1,2), …` in order. Any other character
   aborts as its named construct (a lowercase letter that is not the second
   character of `Cl`/`Br` begins an aromatic atom; `$`/`:` are the out-of-scope
   quadruple/aromatic bonds).

2. **Implicit hydrogens (the pinned bond-order valence rule).** Each
   organic-subset element has a fixed **normal valence** (OpenSMILES "organic
   subset"):

   | element | B | C | N | O | P | S | F | Cl | Br | I |
   |---------|---|---|---|---|---|---|---|----|----|---|
   | normal valence | 3 | 4 | 3 | 2 | 3 | 2 | 1 | 1 | 1 | 1 |

   `P` uses **3**, the OpenSMILES default (`P` also admits 5; not exercised in
   this slice). For each atom, let `deg` be the **sum of the orders of its
   incident bonds**, counting both chain and branch bonds (a single bond
   contributes 1, a double 2, a triple 3): `0` for a lone atom; `1` for a
   single-bonded terminal atom; `2` for a doubly-bonded terminal atom (`=O` in
   formaldehyde) *or* two single bonds; `3`, `4` … similarly (the quaternary
   carbon of `CC(C)(C)C` has `deg = 4`; the central carbon of `O=C=O` has
   `deg = 2 + 2 = 4`). Then

   ```
   implicit_H(atom) = normal_valence(element) − deg
   ```

   **No silent over-bonding.** Before any hydrogen is filled, every atom whose
   `deg` already **exceeds** its normal valence is rejected as `valence-exceeded`
   (e.g. `F=C` puts `deg = 2` on a valence-1 fluorine). So `deg ≤ valence` always
   holds when the subtraction runs, and the result is never negative — there is
   no silent clamp turning an over-bonded atom into a wrong (hydrogen-free)
   formula. (Equivalently `max(0, V − deg)`, but the clamp is unreachable because
   the over-bonded case is a typed abort, not a clamp.)

3. **Atom multiset.** The molecule's atoms are the heavy atoms plus the sum of
   all implicit hydrogens. For a pure length-`L` carbon chain this is the alkane
   multiset `C_L H_(2L+2)`; a heteroatom chain mixes elements, e.g. `CCO`
   gives `{C:2, H:6, O:1}`; a branched skeleton with the same atom count as a
   chain gives the same multiset (`C(CC)C` = `CCCC` = `{C:4, H:10}`).

4. **Hill notation (the canonical written form).** Render the multiset as a
   string in **Hill order**: carbon first (if present), then hydrogen (if
   present), then every other element alphabetically by symbol. A count of `1`
   is written without a digit. This element order is fixed — never dict /
   iteration order — so the bytes are reproducible on any host. (This is the
   simplified Hill convention the molecular-formula language pins: hydrogen is
   always placed second when present, so e.g. ammonia is `H3N` and borane
   `H3B`, regardless of whether carbon is present.)

## Worked examples

| SMILES | atoms | implicit H per atom | multiset | formula (bytes) |
|--------|-------|----------------------|----------|------------------|
| `C`    | C | `4` | `{C:1, H:4}` | `CH4`   |
| `CC`   | C C | `3, 3` | `{C:2, H:6}` | `C2H6`  |
| `CCC`  | C C C | `3, 2, 3` | `{C:3, H:8}` | `C3H8`  |
| `CCO`  | C C O | `3, 2, 1` | `{C:2, H:6, O:1}` | `C2H6O` |
| `CN`   | C N | `3, 2` | `{C:1, H:5, N:1}` | `CH5N` |
| `CF`   | C F | `3, 0` | `{C:1, H:3, F:1}` | `CH3F` |
| `CCl`  | C Cl | `3, 0` | `{C:1, H:3, Cl:1}` | `CH3Cl` |
| `O`    | O | `2` | `{H:2, O:1}` | `H2O` |
| `N`    | N | `3` | `{H:3, N:1}` | `H3N` |
| `NCO`  | N C O | `2, 2, 1` | `{C:1, H:5, N:1, O:1}` | `CH5NO` |

### Branched examples (degree counts branch bonds)

In each, the **parent** atom carries the branch bond, so its degree (and thus
its hydrogen count) reflects the branch. Bonds are listed `(parent, child)`.

| SMILES | atoms | bonds | implicit H per atom | multiset | formula (bytes) |
|--------|-------|-------|----------------------|----------|------------------|
| `C(C)C`     | C C C       | `(0,1) (0,2)`             | `2, 3, 3`     | `{C:3, H:8}`       | `C3H8`   |
| `CC(C)C`    | C C C C     | `(0,1) (1,2) (1,3)`      | `3, 1, 3, 3`  | `{C:4, H:10}`      | `C4H10`  |
| `C(C)(C)C`  | C C C C     | `(0,1) (0,2) (0,3)`      | `1, 3, 3, 3`  | `{C:4, H:10}`      | `C4H10`  |
| `CC(C)(C)C` | C C C C C   | `(0,1) (1,2) (1,3) (1,4)`| `3, 0, 3, 3, 3`| `{C:5, H:12}`     | `C5H12`  |
| `C(O)C`     | C O C       | `(0,1) (0,2)`             | `2, 1, 3`     | `{C:2, H:6, O:1}`  | `C2H6O`  |
| `N(C)C`     | N C C       | `(0,1) (0,2)`             | `1, 3, 3`     | `{C:2, H:7, N:1}`  | `C2H7N`  |
| `C(C(C)C)C` | C C C C C   | `(0,1) (1,2) (1,3) (0,4)`| `2, 1, 3, 3, 3`| `{C:5, H:12}`     | `C5H12`  |
| `C(CC)C`    | C C C C     | `(0,1) (1,2) (0,3)`      | `2, 2, 3, 3`  | `{C:4, H:10}`      | `C4H10`  |

### Bond-order examples (degree is the sum of bond orders)

Bonds are listed `(i, j)·order`; each atom's `deg` is the sum of the orders of
its incident bonds, and `implicit_H = normal_valence − deg`.

| SMILES | atoms | bonds·order | deg per atom | implicit H per atom | multiset | formula (bytes) |
|--------|-------|-------------|--------------|----------------------|----------|------------------|
| `C=C`     | C C     | `(0,1)·2`             | `2, 2`       | `2, 2`        | `{C:2, H:4}`      | `C2H4`  |
| `C#C`     | C C     | `(0,1)·3`             | `3, 3`       | `1, 1`        | `{C:2, H:2}`      | `C2H2`  |
| `C=O`     | C O     | `(0,1)·2`             | `2, 2`       | `2, 0`        | `{C:1, H:2, O:1}` | `CH2O`  |
| `O=C=O`   | O C O   | `(0,1)·2 (1,2)·2`     | `2, 4, 2`    | `0, 0, 0`     | `{C:1, O:2}`      | `CO2`   |
| `CC#N`    | C C N   | `(0,1)·1 (1,2)·3`     | `1, 4, 3`    | `3, 0, 0`     | `{C:2, H:3, N:1}` | `C2H3N` |
| `N#N`     | N N     | `(0,1)·3`             | `3, 3`       | `0, 0`        | `{N:2}`           | `N2`    |
| `C=CC=C`  | C C C C | `(0,1)·2 (1,2)·1 (2,3)·2` | `2, 3, 3, 2` | `2, 1, 1, 2` | `{C:4, H:6}`  | `C4H6`  |
| `C(=O)O`  | C O O   | `(0,1)·2 (0,2)·1`     | `3, 2, 1`    | `1, 0, 1`     | `{C:1, H:2, O:2}` | `CH2O2` |
| `CC(=O)C` | C C O C | `(0,1)·1 (1,2)·2 (1,3)·1` | `1, 4, 2, 1` | `3, 0, 0, 3` | `{C:3, H:6, O:1}` | `C3H6O` |
| `C-C`     | C C     | `(0,1)·1`             | `1, 1`       | `3, 3`        | `{C:2, H:6}`      | `C2H6`  |

The explicit single bond `-` is order 1, identical to the implicit bond, so
`C-C` ≡ `CC` (both `C2H6`). A bond order over an atom's valence (`F=C`, `O#C`,
`N#O`) is a `valence-exceeded` typed abort, not one of these rows.

## Projection `π` and soundness

`π` = the **atom multiset** (and the Hill string that denotes it).
Connectivity (bonds, rings, stereochemistry) is **discarded** — an explicit,
honest loss (PATHS.md §3). The square commutes by construction: the translator
`T` and the carry-back `L` share one source of truth — the molecular-formula
language's `parse`/`to_hill` over the same multiset — so

```
I_smiles(p)  ≡_π  L( I_formula( T(p) ) )
```

is an identity on the atom multiset, checked by the framework oracle on a
heteroatom, branched **and multiply-bonded** corpus
(`tests/test_smiles_formula.py`). Neither branches nor bond orders touch
`T`/`L`: they only change which atom multiset the shared SMILES reader produces
(a double/triple bond just raises the incident atoms' degree, lowering their
implicit-hydrogen count), and the same `parse`/`to_hill` carries it back, so the
square commutes for multiply-bonded molecules by the very same construction.

## Determinism

`T`, `I_smiles`, `I_formula`, `L` are pure functions of their inputs; the only
element-ordering choice (Hill order) is fixed by this spec, and the per-element
valence table above is fixed, so the output bytes are reproducible on any host
and under any `PYTHONHASHSEED`. A twice-and-diff test asserts byte-identical
output (PAIRING.md §5).

## Versioning

The shared SMILES interpreter is at **version 0.4** (AGENTS.md §3): the additive
widening from the single-bonded *tree* (0.3) to a tree whose bonds carry an
**order** — i.e. adding the **double** `=` (order 2), **triple** `#` (order 3),
and explicit **single** `-` (order 1) bond tokens, with the implicit-hydrogen
rule generalized to `normal_valence − Σ bond_orders`. The translator version is
correspondingly **0.4**. Behavior on any string **with no bond token** is
byte-for-byte unchanged across the bump (every chain/branch accepted at 0.3
parses identically at 0.4, with every bond order `1`); 0.3 had added branches
`(...)` to the single-bonded chain (0.2), and 0.2 had widened the carbon-only
chain (0.1) to the full organic subset of bare atoms.
