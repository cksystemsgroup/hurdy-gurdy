# Anchor packs — recorded testimony from Era 4

Every pack is data copied verbatim from tag `era4-final` with a
`PROVENANCE.md` naming what produced it. The file layout is this
generation's (`NNN.program` / `.input` / `.expect` for languages,
`NNN.program` / `.q` for engines, `NNN.program` / `.input` for
corpora); the conventions inside the files are Era 3/4's — a vector's
`.input` is a step count, not a stimulus tape, and a language's
observable names are the ones its Era-3 interpreter exposed (the
pack's `c` reports `halted`/`result`; this generation's `c` reports
`bad`/`depth`). A pack is therefore never agreed with by name: a
regenerated language, pair, or search cites it as an anchor with a
declared reading — which stimulus the step count means, which
observable maps to which — and is admitted against that reading
(`KERNEL.md` §6, §10). Nothing here executes. Packs for `btor2`,
`c`, and `riscv` — languages this generation already holds — are
testimony about the same languages under the older conventions,
consultable by the next revision of each judge through such a
reading, not vectors it must match.

| pack | entry | contents |
|---|---|---|
| `languages/` | `aarch64` | 3 vectors |
| `languages/` | `btor2` | 4 vectors |
| `languages/` | `btor2-spec` | 2 vectors |
| `languages/` | `c` | 3 vectors |
| `languages/` | `crn` | 3 vectors |
| `languages/` | `ebpf` | 3 vectors |
| `languages/` | `evm` | 3 vectors |
| `languages/` | `formula` | 3 vectors |
| `languages/` | `python` | 3 vectors |
| `languages/` | `riscv` | 3 vectors |
| `languages/` | `sail` | 3 vectors |
| `languages/` | `smiles` | 3 vectors |
| `languages/` | `smtlib` | 2 vectors |
| `languages/` | `wasm` | 3 vectors |
| `pairs/` | `aarch64--btor2` | 4 corpus programs (exact) |
| `pairs/` | `aarch64--sail` | 4 corpus programs (exact) |
| `engines/` | `btor2--abc` | 3 programs + engine labels (abc, boolector, btor2tools) |
| `engines/` | `btor2--avr` | 3 programs + engine labels (avr, yices) |
| `engines/` | `btor2--btormc` | 2 programs + engine labels (btormc, boolector) |
| `engines/` | `btor2--enum` | 3 programs + engine labels (hurdy-gurdy:btor2-interp) |
| `engines/` | `btor2--pono-cert` | 3 programs + engine labels (pono, smt-switch, bitwuzla, boolector) |
| `pairs/` | `btor2--smtlib` | 2 corpus programs (exact) |
| `engines/` | `btor2--z3` | 3 programs + engine labels (z3, btor2-smtlib-operator-mapping) |
| `pairs/` | `btor2-spec--havoc` | 2 corpus programs (over) |
| `pairs/` | `btor2-spec--interval` | 2 corpus programs (over) |
| `pairs/` | `c--riscv` | 3 corpus programs (exact) |
| `pairs/` | `crn--smtlib` | 3 corpus programs (exact) |
| `pairs/` | `ebpf--btor2` | 3 corpus programs (exact) |
| `pairs/` | `evm--btor2` | 3 corpus programs (exact) |
| `pairs/` | `python--smtlib` | 3 corpus programs (exact) |
| `pairs/` | `riscv--btor2` | 3 corpus programs (exact) |
| `pairs/` | `riscv--sail` | 3 corpus programs (exact) |
| `pairs/` | `sail--btor2` | 3 corpus programs (exact) |
| `pairs/` | `smiles--formula` | 3 corpus programs (exact) |
| `engines/` | `smtlib--bitwuzla` | 2 programs + engine labels (boolector, bitwuzla) |
| `engines/` | `smtlib--z3` | 2 programs + engine labels (z3) |
| `pairs/` | `wasm--btor2` | 3 corpus programs (exact) |
