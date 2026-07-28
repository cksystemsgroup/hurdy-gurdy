# Pair — `smiles-formula`  ·  SMILES → molecular formula

*Status: **partial** — 17/17 of the construct inventory, still `partial` because the external coverage anchor (RDKit/InChI over a pinned public slice) is not built (the organic-subset graph of single / double / triple bonds
— bare atoms `B C N O P S F Cl Br I` joined by single bonds, **double** `=` and
**triple** `#` bonds, with **branches** `(...)` and **ring-closure bonds** (a
digit `1`-`9` or `%nn` label), and implicit hydrogens; **plus bracket atoms**
`[...]` — any element, explicit H, with isotope / charge / chirality / class
parsed but not counted; **plus stereo bonds** `/` `\` (order 1, direction
discarded) **and dot-disconnected components** `.`; **plus aromaticity** —
lowercase atoms `b c n o p s`, lowercase bracket symbols (`[nH]`, `[se]`) and the
explicit aromatic bond `:`, under a stated one-valence-unit rule; coverage
**17/17**). A compile
pair and field-blindness
witness; ported from v2, widened to the organic-subset heteroatoms (SMILES
interpreter `0.2`), then to branches (`0.3`), then to double/triple/explicit-single
bonds (`0.4`), then to rings (`0.5`), then to bracket atoms (`0.6`), then to
stereo bonds and disconnection (`0.7`), then to aromaticity (SMILES interpreter
`0.8`). The full translation schema is in [`SPEC.md`](./SPEC.md); implementation
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
honest loss ([`ROUTES.md`](../../ROUTES.md) §3). Aromaticity is the one construct
`π` does not simply discard: the lowercase spelling itself *is* discarded (an
aromatic atom's element is its uppercase one), but the hydrogen count the
aromatic rule computes survives — and a hydrogen in the multiset is a hydrogen,
so `T`/`L`/`π` were unchanged by it too.

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

## Built — the organic-subset graph (single / double / triple bonds, chains, branches, rings), bracket atoms, stereo bonds, disconnected components, and aromaticity (17/17)

**Covered constructs (end-to-end through the square):** the **organic-subset
graph of single / double / triple bonds — chains, branches, and rings** — bare
atoms `B C N O P S F Cl Br I` (alongside the original carbon `C`) joined by
implicit single bonds, the explicit single bond `-` (order 1), **double** bonds
`=` (order 2) or **triple** bonds `#` (order 3), optionally with nested
parenthesized **branches** `(...)` and **ring-closure bonds** (a digit `1`-`9` or
two-digit `%nn` label), with implicit hydrogens filled by the pinned per-element
valence rule (`B`3 `C`4 `N`3 `O`2 `P`3 `S`2 `F`/`Cl`/`Br`/`I`1; H =
`normal_valence − degree`, where **degree is the sum of bond orders** and counts
chain, branch, *and ring* bonds) — **plus bracket atoms** `[...]`. Chains may
**mix elements**: `C` → `CH4`, `CCO` → `C2H6O` (ethanol). A **branch** `(...)` is
a sub-chain bonded to the atom it follows (its *parent*): `C(C)C` → `C3H8`,
`CC(C)C` → `C4H10` (isobutane). A **bond token** `= # -` between two atoms sets
the order of the bond joining them: `C=C` → `C2H4` (ethene), `C#C` → `C2H2`
(ethyne), `O=C=O` → `CO2`. A **ring-closure bond** (a digit `1`-`9` or `%nn` label
after an atom; the second occurrence of the same label closes the ring) bonds the
two endpoint atoms, the bond counting toward both their degrees: `C1CCCCC1` →
`C6H12` (cyclohexane), `C1CC1` → `C3H6` (cyclopropane), `C1=CCCCC1` → `C6H10`
(cyclohexene), `O1CCOCC1` → `C4H8O2` (1,4-dioxane), `N1CCCCC1` → `C5H11N`
(piperidine), `C1CCC2CCCCC2C1` → `C10H18` (decalin, fused), `C%10CCCCC%10` →
`C6H12` (two-digit label).

A **bracket atom** `[...]` (OpenSMILES `[ isotope? symbol chirality? hcount?
charge? class? ]`) may name **any element** and carries **explicit hydrogens** —
it gets **no implicit hydrogen** (absent `H` means 0, *not* a valence fill), and
is exempt from the valence rule and check. For the multiset projection only its
**symbol** and **explicit H count** matter: `[NH4+]` → `H4N`, `[CH3]` → `CH3`,
`[13C]` → `C` (isotope discarded), `[OH-]` → `HO` (charge discarded), `[C@H]` →
`CH` (chirality discarded), `[Se]` → `Se`, `[Na]` → `Na`, `[Cu+2]` → `Cu`. A
bracket atom bonds in chains/branches/rings like a bare atom but those bonds
neither add nor remove its hydrogen: `C[N+]C` → `C2H6N` (two bare CH₃ + a bracket
N at 0 H), `[CH3][CH3]` → `C2H6` (ethane), `C[Se]C` → `C2H6Se`, `[CH2]1CC1` →
`C3H6` (a bracket CH₂ in cyclopropane).

An **aromatic atom** is written **lowercase** — bare `b c n o p s`, or a
lowercase bracket symbol (`[nH]`, `[se]`, plus the bracket-only `se`/`as`). It is
the *same element* as its uppercase spelling (the multiset never sees the case)
and spends **one valence unit** on its ring's aromatic system, so implicit H =
`max(0, normal_valence − Σ bond_orders − 1)`. The clamp is the model's whole
content: when the written bonds already fill the valence the atom takes part by
donating a **lone pair** — or, for boron, an empty orbital — which costs nothing.
One line therefore gives benzene `c1ccccc1` → `C6H6`, pyridine `c1ccncc1` →
`C5H5N`, furan `o1cccc1` → `C4H4O`, thiophene `s1cccc1` → `C4H4S`,
N-methylpyrrole `Cn1cccc1` → `C5H7N`, toluene `Cc1ccccc1` → `C7H8`, naphthalene
`c1ccc2ccccc2c1` → `C10H8`, 2-pyridone `O=c1cccc[nH]1` → `C5H5NO`, and adenine
`Nc1ncnc2[nH]cnc12` → `C5H5N5`. A **bracket** aromatic atom keeps its explicit H
and its exemptions, which is how pyrrole is written: `[nH]1cccc1` → `C4H5N`. The
explicit aromatic bond `:` is an order-1 bond asserting both endpoints aromatic,
so `c1:c:c:c:c:c1` ≡ `c1ccccc1`. The full model, including its four typed aborts
and its two stated limits, is [`SPEC.md` § Aromaticity](./SPEC.md).

The translator `T`, the carry-back `L`, and both shared interpreters
(`gurdy/languages/smiles/`, `gurdy/languages/molecular_formula/`) share one source
of truth — the molecular-formula language's `parse`/`to_hill` over the same
multiset — so the square commutes by construction.

This is the **aromaticity widening** (coverage ratchet,
[`BENCHMARKS.md`](../../BENCHMARKS.md) §5): **16/17 → 17/17**, nothing dropped —
the inventory's last construct, on a denominator that has not moved since the
1/17 carbon-only start. It bumped the **shared SMILES interpreter to `0.8`**
(AGENTS.md §3, an additive parse change reading lowercase atoms and the `:`
bond, plus one subtracted-and-clamped valence unit; strings with no lowercase
atom and no `:` parse byte-for-byte as at `0.7`) and the translator to `0.8`.
The earlier **projection-invisible widening** (`14/17 → 16/17`, interp
`0.6 → 0.7`) added the stereo bonds `/` `\` and the dot `.` in one round,
because `π` reads and then discards both. The earlier **bracket-atom
widening** (`10/17 → 14/17`, interp `0.5 → 0.6`) added the bracket grammar; the
molecular-formula
language is already element/multiset-general and needed no change (`to_hill`
already renders any element — `Se`, `Na`, `Fe`, `Cu`, …); the pair's `T`/`L`/`π`
were unchanged (a bracket atom only changes which atom multiset the shared reader
produces). The earlier **ring widening** (`9/17 → 10/17`, interp `0.4 → 0.5`)
added ring-closure bonds; the **bond-order widening** (`6/17 → 9/17`, interp `0.3
→ 0.4`) added double/triple/explicit-single bonds; the **branch widening** (`5/17
→ 6/17`, interp `0.2 → 0.3`) added parenthesized sub-chains; the **heteroatom
widening** (`1/17 → 5/17`, interp `0.1 → 0.2`) generalized the carbon-only chain
to the full organic subset of bare atoms.

**Fidelity: `predicted`.** Evidence: the self-contained schema in
[`SPEC.md`](./SPEC.md) (per-element valence table + the stack-based grammar that
carries a bond order, tracks ring-closure labels, and reads the bracket grammar,
plus the sum-of-orders degree rule, the no-implicit-H bracket rule, and the
one-valence-unit **aromaticity** rule with its clamp) determines
the output bytes (Hill notation gives the canonical, host-independent element
order); a twice-and-diff test (`tests/test_smiles_formula.py`) confirms
byte-identical output for `T` and both interpreters (also verified across
`PYTHONHASHSEED`); the commuting-square oracle aligns `I_s(p) ≡_π L(I_t(T(p)))` on
a heteroatom, branched, multiply-bonded, ring, bracket, stereo, disconnected
**and aromatic** corpus (33 aromatic molecules, benzene through adenine).

**Out-of-scope → typed abort** (`unsupported: smiles:<construct>`,
[`BENCHMARKS.md`](../../BENCHMARKS.md) §3). Construct coverage **17/17** of the
spec-enumerable inventory (`coverage.measure` over
`gurdy/pairs/smiles_formula/inventory.py`) — the histogram is empty for the first
time. In scope: `organic-chain` (the
mixed-element single-bonded chain probe `CCO`), the four heteroatom probes
`organic-atom-N`/`-O`/`-Cl`/`-Br`, `branch` (`C(C)C`), `double-bond` (`C=C`),
`triple-bond` (`C#C`), `explicit-single-bond` (`C-C`), `ring-bond` (`C1CCCCC1`),
the four bracket-atom probes `bracket-atom` (the explicit-H base case
`[CH4]`), `charge` (`[NH4+]`), `isotope` (`[13C]`), `stereo` (`[C@H]`), and now
`stereo-bond` (`F/C=C/F`), `disconnection` (`C.C`), and now `aromatic-atom`
(benzene `c1ccccc1`). A
**malformed branch** (unbalanced/empty parens, `(` with no parent) is itself a
typed abort — `unbalanced-branch` / `branch-without-parent` / `empty-branch`. A
**dangling bond** (a `= # - / \` token with no atom on one side, or one
immediately before a `.`) aborts
`dangling-bond`. A **misplaced dot** — one with no atom on its left (`.C`,
`C..C`, `C(.)C`) or none on its right (`C.`, `C(C.)C`) — aborts
`disconnection-no-atom`, never a silently swallowed token. A **malformed ring closure** — an unclosed label (`C1CC`), a ring
digit with no left atom (`1CCC1`), a self-ring (`C11`), mismatched ring-bond
orders (`C=1CCCCC#1`), or a `%` not followed by two digits (`C%1CC`) — aborts
`ring-bond-unclosed` / `ring-bond-no-atom` / `ring-bond-self` /
`ring-bond-order-mismatch` / `ring-bond-malformed`. A **malformed bracket atom** —
an unclosed `[` (`[`, `[C`, `C[N`), an empty `[]`, an unknown element (`[Xx]`,
`[X]`), a stray `]` (`C]`, `[CH4]]`), the wildcard `[*]`, or a bad
isotope/H/charge/class field (`[1]`, `[+]`, `[C++3]`, `[CHH]`, `[C:]`) — aborts
`bracket-atom-unclosed` / `bracket-atom-empty` / `bracket-atom-element` /
`bracket-atom-malformed`. A **bond order exceeding a *bare* atom's valence**
(`F=C`, `O#C`, or a ring bond that over-bonds an atom, `F1CC1`) aborts
`valence-exceeded` — never a silent wrong formula (a *bracket* atom is exempt). A
**misplaced aromatic atom or bond** is a typed abort too: an aromatic atom on no
ring of aromatic atoms (`cc`, `CcC`, a lone `[nH]`, `c1CCCCC1`, `c1.c1`) aborts
`aromatic-atom-not-in-ring`, a written `=`/`#` between two aromatic atoms
(`c1=cc=cc=c1`) aborts `aromatic-bond-order`, a `:` with a non-aromatic endpoint
(`C:C`) aborts `aromatic-bond-nonaromatic`, and a lowercase symbol outside the
aromatic subset (`x`, `[si]`, `[nh]`) aborts `aromatic-atom:<symbol>` — the
lowercase mirror of `organic-atom:<symbol>`. A
still-unsupported construct does not become reachable just by sitting inside a
branch (`C(C$C)C` still aborts `quadruple-bond`, `C([*])C`
`bracket-atom-malformed`); but
a ring, double/triple bond, bracket atom, stereo bond, dot, **or aromatic ring**
inside a branch *is* in scope
(`C(C1CC1)C` → `C5H10`, `C([N+])C` → `C2H5N`, `C(/F)=C/F` → `C2H2F2`,
`C(C.C)C` → `C4H12`, `C(c1ccccc1)C` → `C8H10`). The `unsupported` histogram
(probe count blocked, by the construct named first under left-to-right parsing)
is **empty**: every probe of the inventory is covered.

What 17/17 does *not* say: the seventeen probes are the constructs this inventory
enumerated at the 1/17 start, and the ratchet has never grown or shrunk that
denominator. Three OpenSMILES tokens were never given a probe of their own and
still hard-abort — the **quadruple bond** `$`, the **wildcard atom** `*`/`[*]`,
and the reaction arrow `>`/`>>`. So 17/17 means "every enumerated construct is
covered", not "every OpenSMILES string parses"; a test asserts those three still
abort, so the honest-failure mechanism cannot quietly lapse behind a full score.

**Tests:** `python -m unittest discover -s tests` (full repo suite; the
`test_smiles_formula` tests pass: per-element / per-molecule / per-branch /
per-bond-order / per-ring / per-bracket / **per-aromatic** vs spec, the
no-implicit-H bracket
rule, twice-and-diff on `T` + both interpreters, the commuting-square check on a
heteroatom + branched + multiply-bonded + ring + bracket + stereo + disconnected
+ **aromatic** corpus, carry-back replay
through `L`, registration smoke, the dangling-bond / valence-exceeded /
malformed-branch / malformed-ring / malformed-bracket /
unsupported-inside-a-branch aborts, the stereo-bond (cis == trans == the
plain single bond) and disconnection (`C.C` is `C2H8`, not `CC`'s `C2H6`;
`C1.C1` closes across the dot; misplaced dots are `disconnection-no-atom`)
checks, the **aromatic** checks — benzene `C6H6` against cyclohexane `C6H12`
(the gap that makes aromaticity not projection-invisible), the clamp on
furan/thiophene/N-methylpyrrole, `[nH]` pyrrole, `:` ≡ adjacency, and the four
aromatic aborts — and the 17/17 coverage/histogram check with
the ratchet asserted not to have dropped anything, plus the assertion that a full
score has not silenced the three unprobed tokens).

**What we learned (PAIRING.md §9) — the 0.8 round.** The last construct was the
only one that was not free, and the round is mostly a record of *where* it cost
something. Three points. (1) **The clamp is the model.** The whole aromaticity
question reduces to one line — `max(0, V − deg − 1)` — and to which of its two
branches an atom lands in. The `− 1` is "this atom spends a bond on the ring's π
system"; the clamp is "it has no room, so it donates a lone pair instead, which
is free". Everywhere else in this pair a `max(0, …)` is a smell — the aliphatic
rule's clamp is deliberately *unreachable*, because reaching it would mean
silently accepting an over-bonded atom. Here it is the load-bearing case, and the
distinction is what the spec had to say out loud: over-bonding is still judged on
the **written** bond orders alone, so the aromatic unit never causes an abort.
Getting that split right is what makes benzene, pyridine, furan, thiophene,
N-methylpyrrole, borinine, 2-pyridone and adenine all come out correct from one
line, with no per-element π table. (2) **A local rule needs a locality
guard.** Because the rule prices *taking part in a ring*, an aromatic atom with
no ring to take part in gets a confidently wrong count rather than an error —
`cc` would read as ethene. The guard is a bridge pass over the **aromatic
subgraph**, not a reading of the ring-closure labels: the labels would make
acceptance depend on where the SMILES walk started, and a spec that prides itself
on byte-reproducibility should not accept a molecule in one spelling and reject
it in another. (3) **17/17 needed a footnote more than it needed a
celebration.** A full score invites the reading "every OpenSMILES string parses",
which is false — `$`, `[*]` and `>>` were never probed. Rather than grow the
denominator (which would break the ratchet's comparability across every earlier
version), the inventory names the three, and a test asserts they still abort; the
number stays honest by saying what it measures.

**What we learned (PAIRING.md §9) — the 0.7 round.** Two constructs landed in one
round on a shared reason: **`π` decides what a widening costs.** A stereo bond
carries geometry and a dot carries connectivity, and the atom multiset keeps
neither — so both reduce to *parse it, then throw the information away*, and the
implicit-hydrogen rule, `T`, `L`, `π`, the molecular-formula language, and the
carry-back were all untouched. Two points worth recording. (1) **The dot is the
one construct that changes the answer by *not* acting.** Every widening before it
either added atoms or added bond order; the dot removes a bond that consecutive
atoms would otherwise have had, so `C.C` is `C2H8` where `CC` is `C2H6` — the
regression test asserts exactly that gap, because a dot silently treated as a
bond (or dropped) would produce a plausible, wrong formula rather than an abort.
(2) **`prev is None` was already the right invariant.** A dot is implemented as
"clear `prev`" — the same state the parser is in before the first atom — so every
token that follows one is judged by a check that already existed: `(` is
`branch-without-parent`, a bond token is `dangling-bond`, a ring label is
`ring-bond-no-atom`. Only the two places that cannot see `prev` (a `)` and
end-of-string) needed the dot's own offset, kept in `pending_dot` purely so the
diagnostic can name it. Ring labels are deliberately *not* cleared at a dot,
which is what makes `C1.C1` — OpenSMILES' spelling for a bond between components
— come out as ethane.

**What we learned (PAIRING.md §9) — the 0.6 round.** The bracket-atom widening was again **purely
additive in the source-language layer** and touched only
`gurdy/languages/smiles/graph.py` (interp bump `0.5` → `0.6`) plus the inventory;
the pair's `T`/`L`/`π` and the molecular-formula language were unchanged. Three
points worth recording: (1) **H is H.** The atom multiset built by the reader is
identical whether a hydrogen is implicit (valence-filled on a bare atom) or
explicit (the `H<n>` of a bracket atom), so carrying the explicit count in the
same `Atom.implicit_h` field meant `atom_multiset`, `T`, `L`, and the whole
carry-back were unchanged — only the *source* of the count differs. (2) **A
bracket atom is a different kind of atom, not a different valence.** The clean cut
was a per-atom `bracket` flag: the degree/`valence-exceeded` pass and the
valence-fill both **skip** bracket atoms (their element need not even be in the
organic-valence table — `[Se]`/`[Na]`/`[Fe]` are accepted), so the existing
valence machinery for bare atoms is untouched and the molecular-formula language
(already element-general) needed no change. (3) **Aromaticity was kept
orthogonal.** At that version a lowercase symbol inside brackets (`[se]`, `[n]`)
aborted the *same* `aromatic-atom` construct a bare lowercase atom did — the
bracket widening added *uppercase/element* bracket symbols only, which is what
made aromaticity a clean separate round at `0.8` (and let `[nH]` land there as an
ordinary bracket atom that happens to be aromatic). Charge, isotope, chirality
and class are parsed and validated (so a
malformed one is a typed abort, never a silent mis-read) but discarded, exactly as
`π` (the multiset) demands.

**Future widening** (coverage ratchet, [`BENCHMARKS.md`](../../BENCHMARKS.md)
§5): the inventory is exhausted, so the ratchet has nowhere left to go and the
next move is a **different kind of evidence**, not a wider scope — the public
coverage anchor (RDKit/InChI canonical formula over a ChEMBL/PubChem slice) as
the external oracle. That is also what would price the two limits this
aromaticity model states rather than checks (no kekulization, no Hückel count)
and the three tokens the inventory never probed (`$`, `[*]`, `>>`): a
sixty-molecule pinned slice measured against RDKit says which of them ever
occur, which is a fact and not a judgment call.

Note: `paper/results/data/capability.json` still records this pair at `14/17` —
it is a snapshot harvested at a commit, regenerated by
`paper/results/harvest.py` (a manual ~40 min run), not by the suite.
