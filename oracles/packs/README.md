# Anchor packs — recorded testimony from Era 4

Every pack is data copied verbatim from tag `era4-final` with a
`PROVENANCE.md` naming what produced it. Vectors and corpora are in
the format this generation's gate reads (`NNN.program` / `.input` /
`.expect`; `NNN.program` / `.q`). Nothing here executes; a pack is
consumed at the admission of a regenerated language, pair, or search
that cites it as an anchor (`KERNEL.md` §6, §10). Packs for `btor2`,
`c`, and `riscv` — languages this generation already holds — are
extra vectors the next revision of each judge must agree on.

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
