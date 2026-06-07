# Design note — sharing the certificate modules across BTOR2 pairs

*Status: deferred (decision recorded 2026-06-04, re-confirmed 2026-06-06;
IR half landed 2026-06-07). No action required for the cert + z3-compiler
relocation until a non-riscv BTOR2 pair actually needs them.*

> **Re-evaluated 2026-06-06 (main-branch audit).** The *certificate-emission*
> trigger has **not** fired: the new `btor2-smtlib` pair
> (`gurdy/pairs/btor2_smtlib/`) consumes BTOR2 and decides it via z3 as a
> native-vs-bridged cross-check; it emits **no** certificates, so it does not
> need these modules. The cert refactor stays deferred.
>
> A *related* signal has appeared, though: `btor2-smtlib` already imports
> `riscv_btor2.btor2.parser` (`from_text`) and `riscv_btor2.btor2.nodes`
> directly (`gurdy/pairs/btor2_smtlib/translate.py:23-24`) — a second,
> non-riscv pair now reaches into the riscv pair's BTOR2 core, the exact
> cross-pair coupling the "Recommended approach" below resolves by extracting
> `gurdy/core/btor2/`. So the **parser/nodes** half of that move now has a real
> second consumer and could be done on its own — smaller than the full
> parser+compiler+certs relocation and independent of cert emission. The four
> bootstrap branches still exist, so the §3 timing concern (do it before the
> next sync) also stands.
>
> **Update 2026-06-07 — the IR (parser/nodes) half landed.** `gurdy/core/btor2/`
> is extracted (commit `29b748b`): the BTOR2 model/parser/printer/evaluator
> moved out of the riscv pair, and `btor2-smtlib` now imports `gurdy.core.btor2`
> — the core-imports-a-pair inversion is **resolved**. Still deferred (no
> consumer yet): the **z3 compiler** (`solvers/_bmc.py`, riscv-internal, zero
> external importers) and the **three cert modules** — both now import the parser
> from core but stay in the riscv pair. They become demand-driven at the first
> branch landing whose solvers want a shared BMC path; relocate them then, with a
> real second consumer in hand (PAIRING.md §15).

## Context

The proved-/unreachable-path certificate prototype currently lives under the
riscv pair:

- `gurdy/pairs/riscv_btor2/lift/certificate.py` — inductive-invariant cert
  (Spacer / Pono ic3sa), re-checked by z3 / bitwuzla / cvc5.
- `gurdy/pairs/riscv_btor2/lift/kind_certificate.py` — k-induction cert
  (Pono `ind`), BASE + STEP discharged in plain z3.
- `gurdy/pairs/riscv_btor2/lift/bmc_certificate.py` — DRAT cert for BMC
  `unreachable` (bitwuzla → cadical → drat-trim).

The other BTOR2-emitting pairs (`aarch64`, `wasm`, `evm`, `ebpf` bootstrap
branches) emit the same BTOR2 format and could in principle reuse all three.
The obvious refactor is to lift these modules into a shared location
(e.g. `gurdy/core/certificates/`) so every BTOR2 pair benefits.

This note records **why that refactor is deferred**, not abandoned.

## The coupling, measured

The three cert modules do **not** depend only on generic SMT machinery. They
import two modules that were riscv-pair-internal when this was measured:

- `riscv_btor2.btor2.parser` → `from_text` *(since 2026-06-07 this is
  `gurdy.core.btor2.parser` — moved to core in Phase B; no longer
  pair-internal, so the parser no longer blocks the cert move)*
- `riscv_btor2.solvers._bmc` → `Compiled, compile_btor2, evaluate_all,
  find_sort_for, bmc` *(still riscv-internal — the remaining blocker)*

Those two dependencies are themselves deeply embedded in the riscv pair:

| Module | Importers across `gurdy` + `bench` |
|---|---|
| `solvers._bmc`   | 10 |
| `btor2.parser`   | 15 |

Consumers of the cert modules, by contrast, are tiny — only two real files,
both under `bench/`:

- `bench/riscv-btor2/oracle_cross.py` (lazy imports *inside functions*)
- `bench/riscv-btor2/prove_certificate_demo.py` (top-level imports)

(`solvers/pono_docker.py` mentions `verify_certificate` only in a docstring.)

There are **no dedicated cert tests**; validation requires running the demo or
`oracle_cross` with Docker + z3 + the corpus.

## Why deferring is the right call

1. **Inverted layering is the real trap.** Moving just the 3 cert files to a
   shared layer would make that shared code import *down* into a specific pair
   (`riscv_btor2.btor2.parser`, `riscv_btor2.solvers._bmc`) — core depending on
   a pair, which is worse than the status quo. A *correct* refactor must also
   relocate the BTOR2 parser and the z3 compiler into the shared layer. That
   turns a 3-file move into a ~25-file move, 10–15 of those files inside the hot
   path of the one pair that currently works. The cheap version and the correct
   version are not the same change.

2. **No consumer needs it yet.** None of the bootstrap pairs currently emit
   certificates. We would be paying the refactor cost (and risk) ahead of any
   demand. The natural trigger is the first bootstrap pair that actually wants
   cert emission — at that point, lift the whole BTOR2 core (parser + compiler +
   certs) together, once, deliberately.

3. **Timing vs. branch merges.** As of 2026-06-04 all four bootstrap branches
   were merged up to `main` and hold byte-identical copies of these files at the
   current paths. Relocating/deleting them on `main` now would make the next
   main→branch sync hit rename/delete reconciliation on exactly those paths,
   partially undoing that clean state. If/when the refactor happens, do it
   **before** the next round of bootstrap merges, not after one.

4. **Validation isn't free.** Zero unit coverage means the only way to know the
   refactor didn't break anything is a Docker-backed demo/oracle run. The
   `oracle_cross` imports are also *lazy inside functions*, so a missed path
   update fails only at runtime on the cert path — easy to ship green-looking
   and broken.

## Recommended approach, when the trigger fires

Do it as one deliberate move, not a piecemeal file shuffle:

1. ✅ *Parser/nodes done (2026-06-07): `gurdy/core/btor2/` exists* (commit
   `29b748b`). Relocate the remaining **generic** machinery into it: the z3
   compiler (`solvers._bmc` generic parts) and — when a pair emits certs — the
   three cert modules.
2. Keep riscv-specific solver glue in the riscv pair; have it import from the
   new shared core.
3. Update all importers (15 parser + 10 `_bmc` + 2 cert consumers) in the same
   change; grep for the lazy `oracle_cross` imports specifically.
4. Land it on `main` **before** the next bootstrap-branch sync, then merge `main`
   into the bootstrap branches so they pick up the shared core cleanly.
5. Add at least one fast cert smoke test that does not require Docker (e.g. the
   k-induction BASE/STEP discharge in plain z3) so future moves are cheap to
   validate.

Until then, the current location is fine: the certs work, they are exercised by
`oracle_cross` and `prove_certificate_demo`, and the only "cost" of leaving them
in the riscv pair is that no other pair can reuse them yet — which is moot while
no other pair emits certificates.
