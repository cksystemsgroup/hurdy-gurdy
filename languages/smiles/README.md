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

*Status: **partial** — built (`gurdy/languages/smiles/`, interpreter **`0.8`**):
the organic-subset **graph of single / double / triple bonds — chains, branches,
and rings — plus bracket atoms, stereo bonds, disconnected components, and
aromatic rings** with
implicit-hydrogen valence filling — bare
atoms `B C N O P S F Cl Br I` joined by single bonds, the explicit single bond
`-`, **double** bonds `=` (order 2) or **triple** bonds `#` (order 3), with nested
parenthesized **branches** `(...)` and **ring-closure bonds** (a digit `1`-`9` or
`%nn` label), **bracket atoms** `[...]` (any element, explicit H), **stereo
(directional) bonds** `/` `\` (order 1, direction discarded), **and
dot-disconnected components** `.` (`C`, `CCO`,
`O`, `CCl`, `C(C)C`, `CC(C)C`, `C=C`, `C#C`, `C=O`, `O=C=O`, `CC#N`, `C(=O)O`,
`C1CCCCC1`, `C1CC1`, `C1=CCCCC1`, `O1CCOCC1`, `[NH4+]`, `[Se]`, `[13C]`, `C[N+]C`,
`F/C=C/F`, `C.C`, `[Na+].[Cl-]`, `c1ccccc1`, `o1cccc1`, `[nH]1cccc1`,
`Cc1ccccc1`, …). For a **bare** atom, implicit H =
`normal_valence − degree` from the
per-element valence table (`B`3 `C`4 `N`3 `O`2 `P`3 `S`2 `F`/`Cl`/`Br`/`I`1; `P`
uses the OpenSMILES default 3), where **degree is the sum of bond orders** (and
counts branch *and ring* bonds; a `.` adds no bond, so the atom after it keeps
the hydrogen a bond would have taken — `C.C` → `C2H8`, not `CC`'s `C2H6`). A
**bracket** atom gets **no implicit hydrogen**
(its H count is the explicit `H<n>` field; absent = 0), may name any element, and
is exempt from the valence rule; its isotope / charge / chirality / atom class are
parsed but do not change the atom multiset. A **lowercase** atom — bare
`b c n o p s`, or a lowercase bracket symbol `[nH]`/`[se]` — is an **aromatic**
atom of the corresponding uppercase element, and spends one valence unit on its
ring's aromatic system: implicit H = `max(0, normal_valence − degree − 1)`, the
clamp being the lone-pair case (`c1ccccc1` → `C6H6` but `o1cccc1` → `C4H4O`).
Every OpenSMILES construct the coverage inventory enumerates is now in scope;
what remains out — the quadruple bond `$`, the wildcard atom `*`/`[*]`, the
reaction arrow, and a lowercase symbol outside the aromatic subset — hard-aborts
`unsupported: smiles:<construct>`
([`BENCHMARKS.md`](../../BENCHMARKS.md) §3); a malformed branch (unbalanced/empty
parens, `(` with no parent), a dangling bond token (no atom on one side), a
malformed ring closure (unclosed label, no left atom, self-ring, mismatched
ring-bond orders, `%` not followed by two digits), a malformed bracket atom
(unclosed `[`, empty `[]`, unknown element, bad H/charge/isotope/class field), a
misplaced dot (`disconnection-no-atom`), a misplaced aromatic atom or bond
(`aromatic-atom-not-in-ring`, `aromatic-bond-order`,
`aromatic-bond-nonaromatic`), and
a bond order exceeding a bare atom's valence are each their own typed abort.
Contributed first by [`smiles-formula`](../../pairs/smiles-formula/README.md).*

**Interpreter versions** (AGENTS.md §3): `0.8` — *additive* widening to
**aromaticity**, the last construct of the inventory and the only one `π` does
*not* discard: it changes the hydrogen count of an atom already in the string
(six aromatic ring carbons carry six H where six saturated ring carbons carry
twelve). Bare lowercase atoms `b c n o p s`, lowercase bracket symbols
(`[nH]`, `[se]`, plus the bracket-only `se`/`as`) and the explicit aromatic bond
`:` come in scope; the element reaching the multiset is the uppercase one. A bare
aromatic atom spends **one valence unit** on its ring's aromatic system, so
implicit H = `max(0, normal_valence − Σ bond_orders − 1)`. The clamp is
load-bearing, not decorative: when the written bonds already fill the valence the
atom takes part by donating a **lone pair** (boron: an empty orbital) instead of
a π electron, which costs nothing — so benzene `c1ccccc1` → `C6H6`, pyridine
`c1ccncc1` → `C5H5N`, and furan `o1cccc1` → `C4H4O` and thiophene `s1cccc1` →
`C4H4S` and N-methylpyrrole `Cn1cccc1` → `C5H7N` all come out right from one
line. Over-bonding is judged on the written orders alone, so the aromatic unit
never causes a `valence-exceeded`. A **bracket** aromatic atom (`[nH]`) keeps its
explicit H and its exemptions — pyrrole `[nH]1cccc1` → `C4H5N`. Three typed
aborts keep the local rule from a confident wrong count: an aromatic atom on no
ring **of aromatic atoms** is `aromatic-atom-not-in-ring` (decided by a bridge
pass over the aromatic subgraph, so it is a property of the molecule and not of
the spelling); a written `=`/`#` between two aromatic atoms is
`aromatic-bond-order` (an exocyclic bond to an aliphatic atom stays in scope —
`O=c1cccc[nH]1` → `C5H5NO`); a `:` with a non-aromatic endpoint is
`aromatic-bond-nonaromatic`. Stated limit: the model is local — no kekulization,
no Hückel count — so a chemically impossible substitution pattern
(`c1ccccc1(C)(C)`) is accepted with zero implicit hydrogens rather than rejected.
Behavior on any string with no lowercase atom and no `:` is byte-for-byte
identical to `0.7`. `0.7` — *additive* widening to the two
**projection-invisible** constructs, in one round because `π` (the atom multiset)
reads and then discards both. **Stereo (directional) bonds** `/` `\` are ordinary
**single bonds (order 1)** whose cis/trans direction is parsed and **discarded**:
`F/C=C/F` (trans) and `F/C=C\F` (cis) both read `C2H2F2`, and `C/C` reads exactly
as `CC` — an explicit, honest loss, never a mis-count. A stereo token obeys every
rule a bond token obeys (a misplaced one aborts `dangling-bond`). The
**dot-disconnection** `.` adds no bond at all: it ends the current component, so
the multiset is the union over components — `C.C` is two methanes `C2H8` (one H
*more* than bonded `CC`), `[Na+].[Cl-]` is `ClNa`. Ring labels survive a dot, so
`C1.C1` — the OpenSMILES spelling for a bond *between* components — is `C2H6`. A
dot with no atom on one side aborts `disconnection-no-atom`. Behavior on any
string with no `/`, `\` or `.` is byte-for-byte identical to `0.6`. `0.6` —
*additive* widening to **bracket
atoms** `[...]` (the OpenSMILES grammar `[ isotope? symbol chirality? hcount?
charge? class? ]`): a bracket atom may name **any element**, gets **no implicit
hydrogen** (its H count is the explicit `H<n>` field; absent = 0), and is exempt
from the valence rule/check; the isotope (`[13C]` is still carbon), charge, stereo
and atom class are parsed but do not change the atom multiset (`[NH4+]` → `H4N`,
`[13C]` → `C`, `[OH-]` → `HO`, `[C@H]` → `CH`, `[Se]` → `Se`). A bracket atom
bonds like a bare atom but its (explicit) hydrogens never change. Behavior on any
string with no bracket atom is byte-for-byte identical to `0.5`. (Aromatic
(lowercase) atoms hard-aborted at that version, bare and in brackets; they came
in at `0.8`.) A malformed bracket (`bracket-atom-unclosed`, `bracket-atom-empty`,
`bracket-atom-element`, `bracket-atom-malformed`) is a typed abort. `0.5` —
*additive* widening to **ring-closure bonds**: a digit `1`-`9` or two-digit `%nn`
label after an atom
marks a ring-bond endpoint, and the second occurrence of the same label closes
the ring by bonding the two endpoint atoms (the bond counting toward both their
degrees; its order is 1, or the order of a bond token written immediately before
the label, `C=1…C1`). The implicit-H rule `normal_valence − Σ bond_orders` is
unchanged (`C1CCCCC1` → `C6H12`, `C1CC1` → `C3H6`, `C1=CCCCC1` → `C6H10`,
`O1CCOCC1` → `C4H8O2`). Behavior on any string with no ring label is
byte-for-byte identical to `0.4`. A malformed ring closure (`ring-bond-unclosed`,
`ring-bond-no-atom`, `ring-bond-self`, `ring-bond-order-mismatch`,
`ring-bond-malformed`) and a ring bond exceeding an atom's valence
(`valence-exceeded`) are typed aborts. `0.4` — *additive* widening to
**double** `=` (order 2) and **triple** `#` (order 3) bonds, plus the explicit
**single** bond `-` (order 1). A bond token between two atoms sets the order of
the bond joining them; an atom's degree is now the *sum of its bond orders*, and
implicit H = `normal_valence − Σ bond_orders` (`C=C` → `C2H4`, `C#C` → `C2H2`,
`C=O` → `CH2O`, `O=C=O` → `CO2`). Behavior on any string with no bond token is
byte-for-byte identical to `0.3` (every bond order is `1`). A dangling bond
(`dangling-bond`) and a valence-exceeding bond (`valence-exceeded`) are typed
aborts. `0.3` — *additive* widening to **branches** `(...)` (a stack-based parse:
a parenthesized sub-chain bonds its first atom to the parent atom it follows,
then the main chain resumes from the parent; possibly nested). Branch-free
behavior is byte-for-byte identical to `0.2`. `0.2` — *additive* widening from
carbon-only to the full organic subset of bare atoms (the valence table above),
so a single-bonded chain may mix elements; carbon-chain behavior unchanged.
`0.1` — the organic-subset carbon chain (carbon valence 4).

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): public molecule
sets (**ChEMBL** / **PubChem** subsets, RDKit's test molecules), pinned.
There is no behavioral verdict; coverage is the fraction of molecules whose
formula matches the **RDKit/InChI** canonical reference (the oracle).

## Pairs over this language

- [`smiles-formula`](../../pairs/smiles-formula/README.md) — source.
