# Translation specification — `smiles-formula` (organic-subset single-bonded tree)

This is the self-contained, reviewable specification the `predicted` fidelity
claim rests on (PAIRING.md §2, §4). Anyone with the SMILES string and this
document can reproduce the translator's output **byte-for-byte**.

## Scope (this slice)

In scope: a non-empty SMILES string that is a **single-bonded tree of
organic-subset bare atoms** and nothing else — a run of the organic-subset
element symbols `B C N O P S F Cl Br I` written outside brackets, joined by
implicit single bonds, optionally with parenthesized **branches** `(...)`
(possibly nested). Examples: `C`, `CC`, `CCC`, … (alkane skeletons); the
heteroatom-mixing chains `CCO` (ethanol), `CN`, `CF`, `CCl`, `O`, `N`, `NCO`;
and the branched skeletons `C(C)C`, `CC(C)C` (isobutane), `C(C)(C)C`,
`CC(C)(C)C` (neopentane), `C(O)C` (dimethyl ether), `N(C)C`, `C(C(C)C)C` … .

Every other OpenSMILES construct is **out of scope** and MUST hard-abort with
`unsupported: smiles:<construct>` (no silent drop). The named out-of-scope
constructs are: ring-bond digits, ring-closure `%`,
double/triple/quadruple/aromatic bonds (`= # $ :`), explicit single bond `-`,
stereo bonds `/ \`, bracket atoms `[...]`, charges `+`, stereo `@`,
disconnection `.`, and aromatic (lowercase) atoms (`c n o s p b`, …). An
uppercase symbol outside the organic subset aborts as `organic-atom:<symbol>`.
A **malformed branch** — an unbalanced parenthesis (`C(`, `C)`, `C(C))`), a
`(` with no parent atom (`(C)C`, `()`), or an empty branch (`C()C`) — is itself
a typed abort (`unbalanced-branch` / `branch-without-parent` / `empty-branch`),
never a silent wrong formula.

## The schema (deterministic, no adaptive choice)

1. **Parse / tokenize (stack-based).** Read the string left to right. At each
   position, the longest organic-subset symbol is one atom: the two-letter
   halogens `Cl` and `Br` are recognized as single atoms (a `C` immediately
   followed by `l` is chlorine, a `B` immediately followed by `r` is bromine —
   *not* carbon+`l` or boron+`r`); every other `B C N O P S F I` is a one-letter
   atom. The parse maintains a single **parent** index `prev` — the atom the
   next atom will bond to (`None` before the first atom) — and a **stack**:

   - An **atom** is appended; if `prev` is not `None`, a single bond
     `(prev, idx)` is added (always `prev < idx`, since indices only grow); then
     `prev` is set to this new atom.
   - `(` **opens a branch**: it pushes the current `prev` (which must not be
     `None` — a `(` with no parent atom is `branch-without-parent`) onto the
     stack. The branch's atoms bond off that same parent.
   - `)` **closes a branch**: it pops the stack (which must be non-empty — an
     unmatched `)` is `unbalanced-branch`) and restores `prev` to the saved
     parent, so the **main chain resumes from the parent**. A branch that
     consumed no atom is `empty-branch`.

   At end-of-string the stack must be empty (an unclosed `(` is
   `unbalanced-branch`). On any branch-free string this is **byte-for-byte the
   old linear behavior**: `prev` walks `0, 1, 2, …` and the bonds come out
   `(0,1), (1,2), …` in order. Any other character aborts as its named construct
   (a lowercase letter that is not the second character of `Cl`/`Br` begins an
   aromatic atom).

2. **Implicit hydrogens (the pinned valence rule).** Each organic-subset element
   has a fixed **normal valence** (OpenSMILES "organic subset"):

   | element | B | C | N | O | P | S | F | Cl | Br | I |
   |---------|---|---|---|---|---|---|---|----|----|---|
   | normal valence | 3 | 4 | 3 | 2 | 3 | 2 | 1 | 1 | 1 | 1 |

   `P` uses **3**, the OpenSMILES default (`P` also admits 5; not exercised in
   this single-bond slice). For each atom, let `deg` be its number of
   single-bond neighbours, **counting both chain and branch bonds** (`0` for a
   lone atom; `1` for a terminal atom or a one-atom branch; `2`, `3`, `4` … for
   an atom carrying that many bonds, e.g. the quaternary carbon of `CC(C)(C)C`
   has `deg = 4`). Then

   ```
   implicit_H(atom) = max(0, normal_valence(element) − deg)
   ```

   The clamp at 0 means an over-bonded atom contributes no negative hydrogens
   (none arises in this single-bond slice; the clamp is there so the rule stays
   total as the slice widens to multiple bonds).

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
heteroatom **and branched** corpus (`tests/test_smiles_formula.py`). Branches do
not touch `T`/`L`: they only change which atom multiset the shared SMILES reader
produces, and the same `parse`/`to_hill` carries it back, so the square commutes
for branched skeletons by the very same construction.

## Determinism

`T`, `I_smiles`, `I_formula`, `L` are pure functions of their inputs; the only
element-ordering choice (Hill order) is fixed by this spec, and the per-element
valence table above is fixed, so the output bytes are reproducible on any host
and under any `PYTHONHASHSEED`. A twice-and-diff test asserts byte-identical
output (PAIRING.md §5).

## Versioning

The shared SMILES interpreter is at **version 0.3** (AGENTS.md §3): the
additive widening from the single-bonded *chain* (0.2) to the single-bonded
*tree* — i.e. adding **branches** `(...)`. The translator version is
correspondingly **0.3**. Branch-free behavior is byte-for-byte unchanged across
the bump (every chain accepted at 0.2 parses identically at 0.3); 0.2 had itself
widened the carbon-only chain (0.1) to the full organic subset of bare atoms.
