# Translation specification — `smiles-formula` (organic-subset graph: single / double / triple bonds, chains, branches, rings, bracket atoms, stereo bonds, disconnection, aromaticity)

This is the self-contained, reviewable specification the `predicted` fidelity
claim rests on (PAIRING.md §2, §4). Anyone with the SMILES string and this
document can reproduce the translator's output **byte-for-byte**.

## Scope (this slice)

In scope: a non-empty SMILES string that is an **organic-subset graph of atoms
joined by single / double / triple bonds — chains, branches, rings, bracket
atoms, stereo bonds, disconnected components, and aromatic rings** — and nothing
else: a run of the organic-subset element symbols
`B C N O P S F Cl Br I` written *bare* (outside brackets), **or any element
written as a bracket atom** `[...]`, joined by **single** bonds (implicit, or the
explicit single bond `-`), **double** bonds `=` (order 2), or **triple** bonds
`#` (order 3), optionally with parenthesized **branches** `(...)` (possibly
nested) and **ring-closure bonds** (a digit `1`-`9`, or a two-digit `%nn` label).
Examples: `C`, `CC`, `CCC`, … (alkane skeletons); the heteroatom-mixing chains
`CCO` (ethanol), `CN`, `CF`, `CCl`, `O`, `N`, `NCO`; the branched skeletons
`C(C)C`, `CC(C)C` (isobutane), `C(C)(C)C`, `CC(C)(C)C` (neopentane), `C(O)C`
(dimethyl ether), `N(C)C`, `C(C(C)C)C` …; the multiply-bonded molecules `C=C`
(ethene), `C#C` (ethyne), `C=O` (formaldehyde), `O=C=O` (carbon dioxide), `CC#N`
(acetonitrile), `N#N`, `C(=O)O` (formic acid), `CC(=O)C` (acetone), `C=CC=C`
(1,3-butadiene), `C-C` (ethane); the **ring** molecules `C1CCCCC1` (cyclohexane),
`C1CC1` (cyclopropane), `C1=CCCCC1` (cyclohexene), `O1CCOCC1` (1,4-dioxane),
`N1CCCCC1` (piperidine), `C1CCC2CCCCC2C1` (decalin), `C%10CCCCC%10` (cyclohexane,
two-digit label) …; and the **bracket-atom** molecules `[NH4+]` (ammonium),
`[CH3]` (methyl), `[13C]` (carbon-13), `[OH-]` (hydroxide), `[Se]` (selenium),
`[Na]`, `[Fe]`, `[C@H]`, `[Cu+2]`, `[CH4]`, `C[N+]C`, `C[Se]C`, `[CH3][CH3]`
(ethane) …; and the **aromatic** molecules `c1ccccc1` (benzene), `c1ccncc1`
(pyridine), `o1cccc1` (furan), `s1cccc1` (thiophene), `[nH]1cccc1` (pyrrole),
`Cc1ccccc1` (toluene), `c1ccc2ccccc2c1` (naphthalene), `Nc1ncnc2[nH]cnc12`
(adenine) … .

A **bracket atom** `[...]` follows the OpenSMILES grammar
`[ isotope? symbol chirality? hcount? charge? class? ]`. For the molecular-formula
projection only its **symbol** and its **explicit H count** (`H<n>`) matter: a
bracket atom gets **no implicit hydrogen** (absent `H` means **zero**, *not* a
valence fill — `[C]` is just C, `[O]` just O), may name **any element** (it is
exempt from the organic-valence table and the valence check), and its **isotope**
(`[13C]` is still carbon), **charge** (`+`/`-`/`++`/`+2`…), **chirality**
(`@`/`@@`) and **atom class** (`:n`) are parsed but do **not** change the atom
multiset.

A **stereo (directional) bond** `/` or `\` is an ordinary **single bond (order
1)**; its up/down direction marks cis/trans configuration around a neighboring
double bond and is parsed but **discarded** — `π` (the atom multiset) keeps no
connectivity, a fortiori no geometry, so `F/C=C/F` (trans) and `F/C=C\F` (cis)
are both `C2H2F2`, and `C/C` is exactly `CC`. A misplaced stereo token is a
`dangling-bond` like any other bond token.

A **dot** `.` is the one token that adds **no bond**: it ends the current
component, so the atom after it opens a new one and the multiset is the **union
over components** — `C.C` is two methanes `C2H8` (one H *more* than bonded `CC`,
since neither carbon spends a bond on the other), `[Na+].[Cl-]` is `ClNa`. Ring
labels are deliberately **not** reset at a dot, so `C1.C1` — the OpenSMILES
spelling for a bond *between* components — is `C2H6`. A dot with no atom on one
side (string start, doubled `..`, before `)`, at end-of-string) aborts
`disconnection-no-atom`; a bond token immediately before it aborts
`dangling-bond`.

An **aromatic atom** is written **lowercase**: bare `b c n o p s` (the
OpenSMILES aromatic organic subset), or a lowercase **bracket** symbol
`[nH]`, `[se]`, `[o+]` (the same six plus `se` and `as`, which OpenSMILES admits
only in brackets). It denotes the *same element* as its uppercase spelling — the
atom multiset never sees the case, so benzene `c1ccccc1` is six **C** — and
records that the atom takes part in a ring's aromatic system. Two atoms that are
adjacent and both aromatic are joined by an **aromatic bond**, which may also be
written explicitly as `:` (`c1:c:c:c:c:c1` ≡ `c1ccccc1`). The full model,
including the hydrogen rule and its four typed aborts, is
[§ Aromaticity](#aromaticity-the-model-this-slice-pins) below.

Every other OpenSMILES construct is **out of scope** and MUST hard-abort with
`unsupported: smiles:<construct>` (no silent drop). The named out-of-scope
constructs are: the quadruple bond `$`, the wildcard atom `*` / `[*]`, the
reaction arrow `>`/`>>`, and a lowercase symbol outside the aromatic subset
(`[si]`, `x`), which aborts `aromatic-atom:<symbol>` — the lowercase mirror of
`organic-atom:<symbol>`.
A bare `+` (charge) or `@` (stereo)
outside a bracket is still out of scope. An uppercase bare symbol outside the
organic subset aborts as `organic-atom:<symbol>`. A **malformed branch** — an
unbalanced parenthesis (`C(`, `C)`, `C(C))`), a `(` with no parent atom (`(C)C`,
`()`), or an empty branch (`C()C`) — is itself a typed abort (`unbalanced-branch`
/ `branch-without-parent` / `empty-branch`). A **dangling bond** — a bond token
`- = #` with no atom on one side (`=C`, `C=`, `C==C`, `C=(C)C`, `C=)`) — is a
typed abort (`dangling-bond`). A **malformed ring closure** — a ring-bond label
never closed (`C1CC`, `C1`), a ring digit with no atom on its left (`1CCC1`), a
self-ring (`C11`), the two ends of one ring bond carrying *different* explicit
orders (`C=1CCCCC#1`), or a `%` not followed by two digits (`C%1CC`, `C%`) — is a
typed abort (`ring-bond-unclosed` / `ring-bond-no-atom` / `ring-bond-self` /
`ring-bond-order-mismatch` / `ring-bond-malformed`). A **malformed bracket atom**
— an unclosed `[` (`[`, `[C`, `C[N`), an empty `[]`, an unknown element symbol
(`[Xx]`, `[X]`), a stray `]` (`C]`, `[CH4]]`), or a bad isotope / H-count / charge
/ class field (`[1]`, `[+]`, `[C++3]`, `[CHH]`, `[C:]`, `[*]`) — is a typed abort
(`bracket-atom-unclosed` / `bracket-atom-empty` / `bracket-atom-element` /
`bracket-atom-malformed`). A **bond order exceeding a *bare* atom's normal
valence** (`F=C` — fluorine valence 1; `O#C` — oxygen valence 2; or a ring bond
that over-bonds an atom, `F1CC1`) is a typed abort (`valence-exceeded`), **never**
a silently clamped-to-zero (wrong) formula. (A *bracket* atom is exempt — its
hydrogens are explicit, so any bond degree is accepted on it.)

## The schema (deterministic, no adaptive choice)

1. **Parse / tokenize (stack-based, carrying a bond order).** Read the string
   left to right. At each position, the longest organic-subset symbol is one
   *bare* atom: the two-letter halogens `Cl` and `Br` are recognized as single
   atoms (a `C` immediately followed by `l` is chlorine, a `B` immediately
   followed by `r` is bromine — *not* carbon+`l` or boron+`r`); every other
   `B C N O P S F I` is a one-letter atom. A `[` instead begins a **bracket
   atom** (see below). The parse maintains a single **parent** index `prev` — the
   atom the next atom will bond to (`None` before the first atom) — a **pending
   bond order** (`1` by default; set to `2` by a `=` token, `3` by `#`, `1` by an
   explicit `-`), and a **stack**:

   - An **atom** (bare or bracket) is appended; if `prev` is not `None`, a bond
     `(prev, idx)` is added with the pending order (always `prev < idx`, since
     indices only grow), and the pending order resets to `1`; then `prev` is set
     to this new atom. A bracket atom bonds exactly like a bare atom.
   - A **bracket atom** `[...]` is read whole (from `[` to the matching `]`) by
     the bracket grammar `[ isotope? symbol chirality? hcount? charge? class? ]`,
     left to right: an optional run of **isotope** digits; the **symbol** (an
     element from the periodic table — a lowercase leading letter names an
     *aromatic* atom of that element and is accepted iff the symbol is in the
     bracket aromatic subset `b c n o p s se as`, else aborts
     `aromatic-atom:<symbol>`; an unknown uppercase symbol aborts
     `bracket-atom-element`, the wildcard `*` is out of scope); an optional
     **chirality** `@`/`@@` (or the extended `@TH1`/`@OH3`/… forms); an optional
     **hcount** `H` then an optional single digit (`H` alone = 1, absent = 0); an
     optional **charge** `+`/`-`, repeated (`++`) or numbered (`+2`); an optional
     **class** `:` then digits. Only the **symbol** and the **hcount** are kept
     (the element, and the explicit hydrogen count) — the isotope, chirality,
     charge and class are validated but discarded, since none change the atom
     multiset. A bracket atom records that it **is** a bracket atom (so step 2
     skips its valence fill and valence check). Any malformed bracket aborts
     (`bracket-atom-unclosed` / `bracket-atom-empty` / `bracket-atom-element` /
     `bracket-atom-malformed`); a `]` with no open `[` aborts `bracket-atom-malformed`.
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
   - A **ring-closure label** — a bare digit `1`-`9`, or a two-digit `%nn` (a `%`
     **must** be followed by exactly two digits, else `ring-bond-malformed`) —
     marks a ring-bond endpoint on the current atom. It **must follow an atom**
     (`prev` not `None`, else `ring-bond-no-atom`). The parse keeps a map
     `open_rings` from label to its opening endpoint. The **first** occurrence of
     a label *opens* it: record `(prev, explicit_order)` — `explicit_order` is
     the order carried by a bond token written immediately before the label (so
     the token is consumed by the ring, not dangling), or "none/default". The
     **second** occurrence of the same label *closes* it: pop the opener and add a
     bond `(open_atom, prev)` (a self-ring `open_atom == prev` is `ring-bond-self`).
     Its order is reconciled from the two ends: if both ends wrote an explicit
     order they must agree (`ring-bond-order-mismatch` otherwise); otherwise the
     one explicit order (or the default `1`) wins. A label *reused after it has
     closed* opens a fresh, independent ring. `prev` is **unchanged** by a ring
     label (the next atom still bonds to the same `prev`).

   At end-of-string the stack must be empty (an unclosed `(` is
   `unbalanced-branch`), no bond token may be open (a trailing `=`/`#`/`-` is
   `dangling-bond`), and `open_rings` must be empty (a ring label opened but never
   closed is `ring-bond-unclosed`). On any string **with no bracket atom** this is
   **byte-for-byte the old behavior**; likewise on any string **with no ring
   label** (`open_rings` stays empty and is never consulted); and on any string
   **with no bond token** it is byte-for-byte the linear/branch behavior: `prev`
   walks `0, 1, 2, …`, every bond order is `1`, and the bonds come out `(0,1),
   (1,2), …` in order. After the parse, and before the hydrogen fill of step 2,
   the three **aromaticity checks** run (§ Aromaticity, in order: a `:` joins two
   aromatic atoms, a bond between two aromatic atoms carries order 1, every
   aromatic atom lies on a ring of aromatic atoms); on a string with no lowercase
   atom and no `:` each is a no-op. Any other character aborts as its named
   construct (a bare
   lowercase letter in `b c n o p s` that is not the second character of
   `Cl`/`Br` is an aromatic atom, any other is `aromatic-atom:<symbol>`; `$` is
   the out-of-scope quadruple bond; a bare
   `+`/`@` is the out-of-scope charge/stereo).

2. **Hydrogens per atom.** A **bracket** atom keeps its **explicit** hydrogen
   count (the `H<n>` field; absent = 0) and is *exempt* from everything below:
   no valence fill, no valence check — aromatic (`[nH]`) or not. A **bare** atom
   gets *implicit* hydrogens
   by the pinned bond-order valence rule. Each organic-subset element has a fixed
   **normal valence** (OpenSMILES "organic subset"), and its lowercase
   (aromatic) spelling uses the same number:

   | element | B | C | N | O | P | S | F | Cl | Br | I |
   |---------|---|---|---|---|---|---|---|----|----|---|
   | normal valence | 3 | 4 | 3 | 2 | 3 | 2 | 1 | 1 | 1 | 1 |

   `P` uses **3**, the OpenSMILES default (`P` also admits 5; not exercised in
   this slice). For each *bare* atom, let `deg` be the **sum of the orders of its
   incident bonds**, counting chain, branch, **and ring-closure** bonds (a single
   bond contributes 1, a double 2, a triple 3, and a ring-closure bond counts
   toward *both* its endpoints): `0` for a lone atom; `1` for a single-bonded
   terminal atom; `2` for a doubly-bonded terminal atom (`=O` in formaldehyde)
   *or* two single bonds (every carbon of cyclohexane `C1CCCCC1` has `deg = 2`:
   one chain bond + one ring bond); `3`, `4` … similarly (the quaternary carbon of
   `CC(C)(C)C` has `deg = 4`; the central carbon of `O=C=O` has `deg = 2 + 2 = 4`;
   each `=C` carbon of cyclohexene `C1=CCCCC1` has `deg = 3`). Then

   ```
   implicit_H(bare aliphatic atom) = normal_valence(element) − deg
   implicit_H(bare aromatic atom)  = max(0, normal_valence(element) − deg − 1)
   explicit_H(bracket atom)        = the H<n> field of the bracket  (no valence rule)
   ```

   The extra `− 1` on the aromatic line is the one valence unit an aromatic atom
   spends on its ring's aromatic system; the clamp is what happens when it does
   not fit. Both are specified in [§ Aromaticity](#aromaticity-the-model-this-slice-pins).

   **No silent over-bonding (bare atoms).** Before any hydrogen is filled, every
   *bare* atom whose `deg` already **exceeds** its normal valence is rejected as
   `valence-exceeded` (e.g. `F=C` puts `deg = 2` on a valence-1 fluorine). So
   `deg ≤ valence` always holds when the subtraction runs, and the result is never
   negative — there is no silent clamp turning an over-bonded atom into a wrong
   (hydrogen-free) formula. (Equivalently `max(0, V − deg)`, but the clamp is
   unreachable because the over-bonded case is a typed abort, not a clamp.) A
   **bracket** atom carries no normal valence here and is **never** valence-checked
   — its hydrogens are written, not inferred, so a bond to a bracket atom changes
   neither its hydrogen count nor its acceptability (any element, any degree).

3. **Atom multiset.** The molecule's atoms are the heavy atoms plus the sum of
   all implicit hydrogens. For a pure length-`L` carbon chain this is the alkane
   multiset `C_L H_(2L+2)`; a heteroatom chain mixes elements, e.g. `CCO`
   gives `{C:2, H:6, O:1}`; a branched skeleton with the same atom count as a
   chain gives the same multiset (`C(CC)C` = `CCCC` = `{C:4, H:10}`); a ring
   *removes two hydrogens* versus the open chain of the same atoms (the two ring
   atoms each gain a bond), so an `L`-membered carbon ring is `C_L H_(2L)` —
   cyclohexane `C1CCCCC1` = `{C:6, H:12}`.

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

### Ring-closure examples (the ring bond counts toward both endpoints)

A ring-closure label (a digit `1`-`9` or `%nn`) after an atom opens a ring-bond
endpoint; the second occurrence closes it, adding a bond between the two endpoint
atoms. The ring bond is one ordinary entry in the bond list — it raises the
degree of *both* its endpoints — so closing a chain into a ring removes exactly
two hydrogens (`C_n H_(2n+2)` chain → `C_n H_2n` ring). Bonds are listed
`(i, j)·order`; the **ring bond is starred** `(i, j)·order*`.

| SMILES | atoms | bonds·order (ring `*`) | deg per atom | implicit H per atom | multiset | formula (bytes) |
|--------|-------|------------------------|--------------|----------------------|----------|------------------|
| `C1CC1`       | C C C       | `(0,1)·1 (1,2)·1 (0,2)·1*`            | `2, 2, 2`       | `2, 2, 2`       | `{C:3, H:6}`       | `C3H6`   |
| `C1CCCCC1`    | C×6         | `(0,1)…(4,5)·1 (0,5)·1*`              | `2,2,2,2,2,2`   | `2,2,2,2,2,2`   | `{C:6, H:12}`      | `C6H12`  |
| `C1=CCCCC1`   | C×6         | `(0,1)·2 (1,2)…(4,5)·1 (0,5)·1*`      | `3,3,2,2,2,2`   | `1,1,2,2,2,2`   | `{C:6, H:10}`      | `C6H10`  |
| `C=1CCCCC1`   | C×6         | `(0,1)…(4,5)·1 (0,5)·2*`              | `3,2,2,2,2,3`   | `1,2,2,2,2,1`   | `{C:6, H:10}`      | `C6H10`  |
| `O1CCOCC1`    | O C C O C C | `(0,1)…(4,5)·1 (0,5)·1*`              | `2,2,2,2,2,2`   | `0,2,2,0,2,2`   | `{C:4, H:8, O:2}`  | `C4H8O2` |
| `N1CCCCC1`    | N C×5       | `(0,1)…(4,5)·1 (0,5)·1*`              | `2,2,2,2,2,2`   | `1,2,2,2,2,2`   | `{C:5, H:11, N:1}` | `C5H11N` |
| `C1CCC2CCCCC2C1` | C×10     | (two ring bonds, `(3,8)*` and `(0,9)*`) | (fusion C: `3`) | (fusion C: `1`) | `{C:10, H:18}`  | `C10H18` |
| `C%10CCCCC%10`| C×6         | `(0,1)…(4,5)·1 (0,5)·1*` (`%10` label)| `2,2,2,2,2,2`   | `2,2,2,2,2,2`   | `{C:6, H:12}`      | `C6H12`  |

The ring bond's order is `1` by default, or the order of a bond token written
immediately **before** the ring digit (`C=1…C1` makes the ring bond a double
bond — contrast `C1=C…` where the `=` is on the *chain* bond after the digit).
If both ends write an explicit order they must agree (`C=1CCCCC#1` is a
`ring-bond-order-mismatch` abort). A label reused after it closes opens a fresh
ring (`C1CCCCC1C1CCCCC1` is two separate cyclohexanes, `C12H22`). An unclosed
label (`C1CC`), a self-ring (`C11`), a ring digit with no left atom (`1CCC1`), a
`%` not followed by two digits (`C%1CC`), and a ring bond that over-bonds an atom
(`F1CC1`) are each a typed abort, not one of these rows.

### Bracket-atom examples (explicit H, no valence fill, no valence check)

A bracket atom `[...]` contributes its **symbol** and its **explicit H count**
(the `H<n>` field; absent = 0). The isotope, chirality, charge and atom class are
parsed but discarded (none change the multiset). A bracket atom is exempt from the
valence rule, so any element and any bond degree is accepted. The "field"
columns below show which bracket fields are present (parsed → discarded unless H).

| SMILES | element | H field | isotope/charge/chir/class | atoms | formula (bytes) |
|--------|---------|---------|---------------------------|-------|------------------|
| `[NH4+]`  | N  | `H4` → 4 | charge `+` (discarded)        | `{H:4, N:1}` | `H4N` |
| `[CH3]`   | C  | `H3` → 3 | —                              | `{C:1, H:3}` | `CH3` |
| `[13C]`   | C  | none → 0 | isotope `13` (discarded)       | `{C:1}`      | `C`   |
| `[OH-]`   | O  | `H` → 1  | charge `-` (discarded)         | `{H:1, O:1}` | `HO`  |
| `[Se]`    | Se | none → 0 | —                              | `{Se:1}`     | `Se`  |
| `[C@H]`   | C  | `H` → 1  | chirality `@` (discarded)      | `{C:1, H:1}` | `CH`  |
| `[C]`     | C  | none → 0 | —                              | `{C:1}`      | `C`   |
| `[Na]`    | Na | none → 0 | —                              | `{Na:1}`     | `Na`  |
| `[Cu+2]`  | Cu | none → 0 | charge `+2` (discarded)        | `{Cu:1}`     | `Cu`  |
| `[CH4]`   | C  | `H4` → 4 | —                              | `{C:1, H:4}` | `CH4` |
| `[15NH4+]`| N  | `H4` → 4 | isotope `15` + charge `+`      | `{H:4, N:1}` | `H4N` |
| `[CH3:1]` | C  | `H3` → 3 | class `:1` (discarded)         | `{C:1, H:3}` | `CH3` |

A bracket atom **bonds like a bare atom** but its hydrogens never change. So a
bracket atom in a chain/branch/ring contributes its explicit H regardless of
degree, while its **bare** neighbours still valence-fill: `C[N+]C` is `C2H6N`
(the two bare CH₃ at 3 H each + the bracket N at 0 H), `[CH3][CH3]` is `C2H6`
(ethane, two bracket methyls), `C[Se]C` is `C2H6Se`, `[CH2]1CC1` is `C3H6`
(cyclopropane with one bracket CH₂). An unclosed `[`, an empty `[]`, an unknown
element `[Xx]`, the wildcard `[*]`, and a bad H/charge/isotope/class field (`[1]`,
`[+]`, `[C++3]`, `[CHH]`, `[C:]`) are each a typed abort, not one of these rows;
a lowercase bracket symbol in the aromatic subset (`[se]`, `[nH]`) is an
*aromatic* bracket atom (§ Aromaticity), and one outside it (`[si]`) aborts
`aromatic-atom:<symbol>`.

## Aromaticity — the model this slice pins

Aromaticity is the one construct `π` does **not** discard. Every widening before
it either added atoms or added bond order, and the atom multiset either kept the
information or threw it away; an aromatic atom instead changes **how many
hydrogens an atom already in the string gets**. Six aromatic ring carbons carry
six hydrogens where six single-bonded ring carbons carry twelve — so a lowercase
atom read as its uppercase spelling would give benzene `C6H12`: a plausible,
wrong formula, exactly the failure this pair aborts rather than emits. That is
why aromaticity needs a stated model and not just a parse, and the model is here.

### 1. Which symbols

**Bare** (outside brackets): `b c n o p s` — the OpenSMILES *aromatic organic
subset*, the lowercase spelling of the six organic-subset elements that can be
aromatic. There is no bare two-letter aromatic symbol.

**In brackets**: the same six plus `se` and `as` (`[nH]`, `[se]`, `[o+]`,
`[as]`), which OpenSMILES admits only in brackets. In the lowercase spelling a
two-letter symbol is *two lowercase letters*, so a following lowercase letter is
part of the symbol and a following uppercase one is the next field: `[se]` reads
as `se`, `[nH]` as `n` plus the `H` field.

The **element** is the uppercase form (`c` → `C`, `se` → `Se`); the case records
ring participation, not a different element, and never reaches the multiset. Its
**normal valence** is the element's own entry in the table of §2 above. A
lowercase symbol outside these sets is a typed abort `aromatic-atom:<symbol>`.

### 2. The hydrogen rule — one valence unit, clamped

An aromatic atom takes part in its ring's π system. In this degree model that
participation costs **one unit of valence** — the *+1 for the aromatic system*
convention — *when the atom's written bonds leave room for it*. When they do
not, the atom takes part by donating a **lone pair** instead (or, for boron, by
lending an empty orbital), which costs nothing. So, with `deg` the sum of the
atom's written bond orders exactly as in §2:

```
implicit_H(bare aromatic atom) = max(0, normal_valence − deg − 1)
```

Here the `max(0, …)` is **load-bearing**, in deliberate contrast to the
aliphatic rule where it is unreachable. It is the exact point at which the model
switches from *contributes a π electron* to *contributes a lone pair*, and it is
what answers the question a naive `+1` gets wrong:

| SMILES | atom | valence | deg | `V − deg − 1` | implicit H | molecule |
|--------|------|---------|-----|---------------|------------|----------|
| `c1ccccc1`   | `c` | 4 | 2 | 1 | **1** | benzene `C6H6` |
| `c1ccncc1`   | `n` | 3 | 2 | 0 | **0** | pyridine `C5H5N` |
| `o1cccc1`    | `o` | 2 | 2 | −1 | **0** *(clamped)* | furan `C4H4O` |
| `s1cccc1`    | `s` | 2 | 2 | −1 | **0** *(clamped)* | thiophene `C4H4S` |
| `Cn1cccc1`   | `n` | 3 | 3 | −1 | **0** *(clamped)* | N-methylpyrrole `C5H7N` |
| `Cc1ccccc1`  | ipso `c` | 4 | 3 | 0 | **0** | toluene `C7H8` |
| `b1ccccc1`   | `b` | 3 | 2 | 0 | **0** | borinine `C5H5B` |

**Furan's `o` is the case the naive rule gets wrong.** Oxygen's normal valence is
2 and its two ring bonds already spend it, so an unconditional `+1` would put
`deg = 3` on a valence-2 atom and abort `valence-exceeded` — rejecting a real,
ordinary molecule. Chemistry says why it should not: furan's oxygen joins the
aromatic sextet with a **lone pair**, not with a π electron, and a lone pair
costs no valence. The clamp is that sentence written as one `max`. The same
clamp covers thiophene's `s` and the three-connected `n` of N-methylpyrrole,
where the third bond is *written* rather than implied.

**Over-bonding is judged on the written orders alone.** A bare aromatic atom
aborts `valence-exceeded` iff `deg > normal_valence`. The aromatic unit never
causes that abort, because an atom with no room simply does not spend it.

**Pyrrole is written in brackets.** A bare `n` in a five-ring gets no hydrogen
under this rule (`3 − 2 − 1 = 0`), which is the pyrrolyl anion — and that is
OpenSMILES's own convention: pyrrole is `[nH]1cccc1`, where the bracket atom
carries its hydrogen explicitly. `C4H5N`, correctly.

### 3. Bonds between aromatic atoms

Two adjacent aromatic atoms are joined by an **aromatic bond**, of order 1 for
the degree rule. It may be written implicitly (adjacency), as an explicit single
bond `-` (the inter-ring bond of a biphenyl, `c1ccccc1-c1ccccc1`), as a stereo
bond `/` `\`, or as the explicit aromatic bond `:`. Writing it changes nothing:
`c1:c:c:c:c:c1` ≡ `c1ccccc1` ≡ `C6H6`.

A bond to an **aliphatic** atom is an ordinary bond of whatever order is
written, aromatic endpoint or not — so an exocyclic double bond onto an aromatic
atom is in scope: `O=c1cccc[nH]1` is 2-pyridone, `C5H5NO`.

### 4. The four typed aborts

A local hydrogen rule can be confidently wrong on a string that is not a
molecule, so four cases are typed aborts rather than formulas:

| construct | when | example |
|-----------|------|---------|
| `aromatic-atom-not-in-ring` | an aromatic atom lies on no ring **of aromatic atoms** | `cc`, `CcC`, a lone `[nH]`, `c1CCCCC1`, `c1.c1` |
| `aromatic-bond-order` | a written `=`/`#` joins two aromatic atoms (a lowercase Kekulé spelling) | `c1=cc=cc=c1` |
| `aromatic-bond-nonaromatic` | a `:` has an endpoint that is not an aromatic atom | `C:C` |
| `aromatic-atom:<symbol>` | a lowercase symbol outside the subset | `x`, `[si]`, `[fe]`, `[nh]` |

The ring requirement is what the hydrogen rule is *priced against*: it spends a
valence unit on taking part in a ring, so an aromatic atom with no ring to take
part in would get a confident wrong count. Ring membership is decided on the
**aromatic subgraph** — the aromatic atoms together with the bonds whose both
endpoints are aromatic — by asking whether the atom is incident to a
non-bridge edge (one iterative Tarjan pass). Deciding it on the subgraph rather
than on the ring-closure labels is what makes it a property of the *molecule*
and not of the *spelling*: tetralin `C1CCc2ccccc2C1` passes (its benzene ring is
all-aromatic) and `c1.c1` fails (the ring label does close across the dot, but
one bond is not a ring), whichever atom the SMILES walk happened to start from.

### 5. What this model does not do

The model is **local**: it prices one atom at a time from its own written bonds
and its own element. It does **not** kekulize, and it does **not** check that a
ring's π system is electronically consistent (no Hückel count). Two consequences,
stated rather than hidden:

- An aromatic ring written with a chemically impossible substitution pattern —
  `c1ccccc1(C)(C)`, an aromatic carbon with four σ neighbours — is **accepted**
  with zero implicit hydrogens rather than rejected. Only the written bond
  orders are valence-checked.
- A ring of aromatic atoms that could not actually be aromatic (wrong electron
  count) is accepted and priced by the same rule.

Both are the honest cost of a rule that needs no global analysis; neither can
turn an in-scope molecule into a wrong formula, because the rule is exact
wherever the written bonds and the element determine the answer — which is every
molecule in the corpus of `tests/test_smiles_formula.py`, from benzene to
adenine `Nc1ncnc2[nH]cnc12` → `C5H5N5`.

### Aromatic examples

| SMILES | molecule | per-atom implicit H | formula (bytes) |
|--------|----------|---------------------|------------------|
| `c1ccccc1`          | benzene         | `1` ×6                        | `C6H6`   |
| `c1:c:c:c:c:c1`     | benzene (explicit `:`) | `1` ×6                 | `C6H6`   |
| `c1ccncc1`          | pyridine        | c `1` ×5, n `0`               | `C5H5N`  |
| `o1cccc1`           | furan           | o `0`, c `1` ×4               | `C4H4O`  |
| `s1cccc1`           | thiophene       | s `0`, c `1` ×4               | `C4H4S`  |
| `[nH]1cccc1`        | pyrrole         | [nH] `1` (explicit), c `1` ×4 | `C4H5N`  |
| `Cn1cccc1`          | N-methylpyrrole | C `3`, n `0`, c `1` ×4        | `C5H7N`  |
| `c1cnc[nH]1`        | imidazole       | c `1` ×3, n `0`, [nH] `1`     | `C3H4N2` |
| `Cc1ccccc1`         | toluene         | C `3`, ipso c `0`, c `1` ×5   | `C7H8`   |
| `Oc1ccccc1`         | phenol          | O `1`, ipso c `0`, c `1` ×5   | `C6H6O`  |
| `O=c1cccc[nH]1`     | 2-pyridone      | O `0`, c(=O) `0`, c `1` ×4, [nH] `1` | `C5H5NO` |
| `c1ccc2ccccc2c1`    | naphthalene     | fusion c `0` ×2, c `1` ×8     | `C10H8`  |
| `c1ccc2ncccc2c1`    | quinoline       | fusion c `0` ×2, n `0`, c `1` ×7 | `C9H7N` |
| `Nc1ncnc2[nH]cnc12` | adenine         | N `2`, n `0` ×3, [nH] `1`, c `1` ×2, c `0` ×3 | `C5H5N5` |
| `c1ccccc1c1ccccc1`  | biphenyl        | junction c `0` ×2, c `1` ×10  | `C12H10` |
| `C1CCc2ccccc2C1`    | tetralin        | aliphatic C `2` ×4, fusion c `0` ×2, c `1` ×4 | `C10H12` |
| `b1ccccc1`          | borinine        | b `0`, c `1` ×5               | `C5H5B`  |
| `p1ccccc1`          | phosphinine     | p `0`, c `1` ×5               | `C5H5P`  |

## Projection `π` and soundness

`π` = the **atom multiset** (and the Hill string that denotes it).
Connectivity (bonds, rings, stereochemistry) is **discarded** — an explicit,
honest loss (ROUTES.md §3). The square commutes by construction: the translator
`T` and the carry-back `L` share one source of truth — the molecular-formula
language's `parse`/`to_hill` over the same multiset — so

```
I_smiles(p)  ≡_π  L( I_formula( T(p) ) )
```

is an identity on the atom multiset, checked by the framework oracle on a
heteroatom, branched, multiply-bonded, ring, bracket, stereo, disconnected **and
aromatic** corpus
(`tests/test_smiles_formula.py`). Neither branches, bond orders, rings, bracket
atoms, **nor aromaticity** touch `T`/`L`: they only change which atom multiset the
shared
SMILES reader produces (a bracket atom just contributes its element + its explicit
H — and a ring-closure bond just adds one more bond, raising its two endpoints'
degree and lowering their *bare*-atom implicit-hydrogen count), and the same
`parse`/`to_hill` carries it back, so the square commutes for bracket molecules by
the very same construction. The atom multiset built by the reader is identical
whether a hydrogen is implicit (valence-filled on a bare atom) or explicit (the
`H<n>` of a bracket atom) — H is H — so the carry-back is the same trivial
re-projection.

**Aromaticity is the one construct that is not simply discarded**, and it is
worth being exact about *what* survives. What `π` discards is the same as ever:
the bonds, the rings, the geometry — and the *lowercase spelling* itself, since
an aromatic atom's element is its uppercase one. What survives is only the
**hydrogen count** the aromatic rule computed, and a hydrogen is a hydrogen in
the multiset like any other. So `T`, `L`, `π`, the molecular-formula language and
the carry-back are untouched here too: aromaticity changes the reader's arithmetic
(one more subtracted unit, clamped), never the shape of what crosses the square.

## Determinism

`T`, `I_smiles`, `I_formula`, `L` are pure functions of their inputs; the only
element-ordering choice (Hill order) is fixed by this spec, and the per-element
valence table and the bracket element set above are fixed, so the output bytes
are reproducible on any host and under any `PYTHONHASHSEED`. A twice-and-diff test
asserts byte-identical output (PAIRING.md §5). The bracket parse is a single
left-to-right scan with no dict-iteration reaching the bytes.

## Versioning

The shared SMILES interpreter is at **version 0.8** (AGENTS.md §3): the additive
widening to **aromaticity** — bare lowercase atoms `b c n o p s`, lowercase
bracket symbols (`[nH]`, `[se]`) and the explicit aromatic bond `:` — under the
one-valence-unit rule `max(0, V − deg − 1)` specified in
[§ Aromaticity](#aromaticity-the-model-this-slice-pins) above. It is the **last**
construct of the inventory and the only one `π` does not discard: unlike every
widening before it, it changes the hydrogen count of an atom already in the
string. The translator version is correspondingly **0.8**. Behavior on any
string **with no lowercase atom and no `:`** is byte-for-byte unchanged across
the bump (every chain/branch/bond/ring/bracket/stereo/dot string accepted at 0.7
parses identically at 0.8).

0.7 had added the additive
widening to the two **projection-invisible** constructs — **stereo (directional)
bonds** `/` `\` (order-1 bonds whose direction is parsed and discarded) and the
**dot-disconnection** `.` (a component break that adds no bond, so the multiset
is the union over components). They land in one round because `π` reads and then
discards both: geometry and connectivity are exactly what the atom multiset does
not keep. The bare-atom implicit-hydrogen rule `normal_valence − Σ bond_orders`
is unchanged — a dot simply contributes no bond order to either side. The
Behavior on any string **with no
`/`, `\` or `.`** was byte-for-byte unchanged across that bump (every
chain/branch/bond/ring/bracket accepted at 0.6 parses identically at 0.7).

0.6 had added **bracket atoms** `[...]` — the OpenSMILES bracket grammar
`[ isotope? symbol chirality? hcount? charge? class? ]`. A bracket atom may name
**any element**, gets **no implicit hydrogen** (its H count is the explicit
`H<n>` field; absent = 0), and is exempt from the valence rule and check; the
isotope, charge, chirality and atom class are parsed but do not change the atom
multiset. Behavior on any
string **with no bracket atom** was byte-for-byte unchanged across that bump
(every
chain/branch/bond/ring accepted at 0.5 parses identically at 0.6); 0.5 had added
**ring-closure bonds** to the tree (0.4), 0.4 had added the double `=` / triple
`#` / explicit single `-` bond tokens to the single-bonded tree (0.3), 0.3 had
added branches `(...)` to the single-bonded chain (0.2), and 0.2 had widened the
carbon-only chain (0.1) to the full organic subset of bare atoms.
