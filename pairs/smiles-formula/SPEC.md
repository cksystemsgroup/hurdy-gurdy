# Translation specification — `smiles-formula` (organic-subset chain)

This is the self-contained, reviewable specification the `predicted` fidelity
claim rests on (PAIRING.md §2, §4). Anyone with the SMILES string and this
document can reproduce the translator's output **byte-for-byte**.

## Scope (this slice)

In scope: a non-empty SMILES string that is a **linear single-bonded chain of
organic-subset bare atoms** and nothing else — a run of the organic-subset
element symbols `B C N O P S F Cl Br I` written outside brackets, joined by
implicit single bonds. Examples: `C`, `CC`, `CCC`, … (alkane skeletons), and the
heteroatom-mixing chains `CCO` (ethanol), `CN`, `CF`, `CCl`, `O`, `N`, `NCO`, …

Every other OpenSMILES construct is **out of scope** and MUST hard-abort with
`unsupported: smiles:<construct>` (no silent drop). The named out-of-scope
constructs are: branches `()`, ring-bond digits, ring-closure `%`,
double/triple/quadruple/aromatic bonds (`= # $ :`), explicit single bond `-`,
stereo bonds `/ \`, bracket atoms `[...]`, charges `+`, stereo `@`,
disconnection `.`, and aromatic (lowercase) atoms (`c n o s p b`, …). An
uppercase symbol outside the organic subset aborts as `organic-atom:<symbol>`.

## The schema (deterministic, no adaptive choice)

1. **Parse / tokenize.** Read the string left to right. At each position, the
   longest organic-subset symbol is one atom: the two-letter halogens `Cl` and
   `Br` are recognized as single atoms (a `C` immediately followed by `l` is
   chlorine, a `B` immediately followed by `r` is bromine — *not* carbon+`l` or
   boron+`r`); every other `B C N O P S F I` is a one-letter atom. Consecutive
   atoms are joined by a single bond, in order: a length-`L` chain (counting
   atoms, so `Cl`/`Br` count as one) yields atoms `0..L-1` and single bonds
   `(i, i+1)` for `0 ≤ i < L-1`. Any other character aborts as its named
   construct (a lowercase letter that is not the second character of `Cl`/`Br`
   begins an aromatic atom).

2. **Implicit hydrogens (the pinned valence rule).** Each organic-subset element
   has a fixed **normal valence** (OpenSMILES "organic subset"):

   | element | B | C | N | O | P | S | F | Cl | Br | I |
   |---------|---|---|---|---|---|---|---|----|----|---|
   | normal valence | 3 | 4 | 3 | 2 | 3 | 2 | 1 | 1 | 1 | 1 |

   `P` uses **3**, the OpenSMILES default (`P` also admits 5; not exercised in
   this single-bond slice). For each atom, let `deg` be its number of
   single-bond neighbours (`0` for a lone atom, `1` at each chain end, `2` in
   the interior). Then

   ```
   implicit_H(atom) = max(0, normal_valence(element) − deg)
   ```

   The clamp at 0 means an over-bonded atom contributes no negative hydrogens
   (none arises in this single-bond slice; the clamp is there so the rule stays
   total as the slice widens to multiple bonds).

3. **Atom multiset.** The molecule's atoms are the heavy atoms plus the sum of
   all implicit hydrogens. For a pure length-`L` carbon chain this is the alkane
   multiset `C_L H_(2L+2)`; a heteroatom chain mixes elements, e.g. `CCO`
   gives `{C:2, H:6, O:1}`.

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
heteroatom corpus (`tests/test_smiles_formula.py`).

## Determinism

`T`, `I_smiles`, `I_formula`, `L` are pure functions of their inputs; the only
element-ordering choice (Hill order) is fixed by this spec, and the per-element
valence table above is fixed, so the output bytes are reproducible on any host
and under any `PYTHONHASHSEED`. A twice-and-diff test asserts byte-identical
output (PAIRING.md §5).

## Versioning

The shared SMILES interpreter is at **version 0.2** (AGENTS.md §3): the
additive widening from the carbon-only chain (0.1) to the full organic subset
of bare atoms. The translator version is correspondingly **0.2**. Carbon-chain
behavior is unchanged across the bump.
