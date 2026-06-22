# Translation specification — `smiles-formula` (thin slice)

This is the self-contained, reviewable specification the `predicted` fidelity
claim rests on (PAIRING.md §2, §4). Anyone with the SMILES string and this
document can reproduce the translator's output **byte-for-byte**.

## Scope (this slice)

In scope: a non-empty SMILES string that is a run of the organic-subset
character `C` and nothing else — `C`, `CC`, `CCC`, ... (the alkane carbon
skeleton with implicit hydrogens). Every other OpenSMILES construct is **out of
scope** and MUST hard-abort with `unsupported: smiles:<construct>` (no silent
drop). The named out-of-scope constructs are: branches `()`, ring-bond digits,
ring-closure `%`, double/triple/quadruple/aromatic bonds (`= # $ :`), explicit
single bond `-`, stereo bonds `/ \`, bracket atoms `[...]`, charges `+ -`,
isotopes, stereo `@`, disconnection `.`, aromatic (lowercase) atoms, and every
organic atom other than carbon (`N O P S F Cl Br I B`).

## The schema (deterministic, no adaptive choice)

1. **Parse.** Read the string left to right. Each `C` is one carbon atom.
   Consecutive carbons are joined by a single bond, in order: a length-`L`
   string yields carbons `0..L-1` and single bonds `(i, i+1)` for `0 ≤ i < L-1`.
   A `C` immediately followed by `l` is chlorine `Cl` (out of scope — abort,
   do not read it as carbon). Any other character aborts as its named
   construct.

2. **Implicit hydrogens (the pinned valence rule).** Organic-subset carbon has
   **normal valence 4**. For each carbon, let `deg` be its number of
   single-bond neighbours (`0` for a lone atom, `1` at each chain end, `2` in
   the interior). Then

   ```
   implicit_H(carbon) = valence(C) − deg = 4 − deg     (≥ 0 in this slice)
   ```

3. **Atom multiset.** The molecule's atoms are the carbons plus the sum of all
   implicit hydrogens: `{ C: L, H: Σ_i (4 − deg_i) }`. For a length-`L` carbon
   chain this is the alkane multiset `C_L H_(2L+2)` (the two ends contribute 3
   H each, every interior carbon 2 H).

4. **Hill notation (the canonical written form).** Render the multiset as a
   string in **Hill order**: carbon first (if present), then hydrogen (if
   present), then every other element alphabetically by symbol. A count of `1`
   is written without a digit. This element order is fixed — never dict /
   iteration order — so the bytes are reproducible on any host.

## Worked examples

| SMILES | carbons | implicit H per carbon | multiset | formula (bytes) |
|--------|---------|------------------------|----------|------------------|
| `C`    | 1 | `4` | `{C:1, H:4}` | `CH4`   |
| `CC`   | 2 | `3, 3` | `{C:2, H:6}` | `C2H6`  |
| `CCC`  | 3 | `3, 2, 3` | `{C:3, H:8}` | `C3H8`  |
| `CCCC` | 4 | `3, 2, 2, 3` | `{C:4, H:10}` | `C4H10` |

## Projection `π` and soundness

`π` = the **atom multiset** (and the Hill string that denotes it).
Connectivity (bonds, rings, stereochemistry) is **discarded** — an explicit,
honest loss (PATHS.md §3). The square commutes by construction: the translator
`T` and the carry-back `L` share one source of truth — the molecular-formula
language's `parse`/`to_hill` over the same multiset — so

```
I_smiles(p)  ≡_π  L( I_formula( T(p) ) )
```

is an identity on the atom multiset, checked by the framework oracle on a small
corpus (`tests/test_smiles_formula.py`).

## Determinism

`T`, `I_smiles`, `I_formula`, `L` are pure functions of their inputs; the only
element-ordering choice (Hill order) is fixed by this spec. A twice-and-diff
test asserts byte-identical output (PAIRING.md §5).
