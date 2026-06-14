# Playbook — implement a pair (differential-only)

You are an autonomous builder on branch `pairs/<id>`. Your contract is
`registry/<id>.yaml`. Implement the hop so the gate certifies it at the
manifest's `fidelity.target`.

## Hard rules (the gate enforces these; violating them fails merge)

1. **You may not read or execute Sail.** `oracle_access: differential_only`.
   Build the lowering from the ISA manual and your own model. Your only
   behavioral reference is `dev_oracle` (e.g. Spike) — use it freely.
2. **You may not use the `machine_tool` path during construction.** It is
   Sail-derived; using it would destroy your independence (and your ability
   to *validate* Sail). It is a runtime path only. `construction: forbidden`.
3. **You may not change `projection` or `fidelity.target`.** They are pinned
   in the manifest and byte-checked by the gate.

## Loop

1. Read the contract: `in_lang`, `out_lang`, `projection`, `target`,
   `reasoning.solvers`.
2. Implement `translate` (and, if `machine_tool` is declared, the `machine`
   path as a thin delegation to `tools.sail_btor2_machine.instantiate` — wire
   it but do not exercise it to derive your own lowering) and `lift`.
3. Self-test against `dev_oracle` on instances you generate. Iterate.
4. Run the gate locally: `python cli.py gate <id>`. It runs F0 now and the
   higher checks as they come online. Treat its report as feedback, not as
   the verdict — the merge verdict comes from the gate on a clean checkout.
5. Open a PR `pairs/<id> -> <merge_branch>`. The gate decides.

## What "done" means

`python cli.py gate <id>` reports `level >= target`, the reasoning-side
differential trust passes, and the independence audit is clean.
