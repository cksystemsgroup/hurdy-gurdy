# Playbook — self-check (both agent types)

Before opening a PR, run the gate locally and read the report.

```bash
cd v3
python cli.py gate <id>          # pair builders
# machine builders: drive tools/sail_btor2_machine/{generate,verify}.py
```

## Reading the report

- `level` — the highest fidelity check that PASSed with no FAIL below it.
- `merge` — the merge policy's decision and its reasons. A non-empty reason
  list means blocked; fix the first reason and re-run.

## Common blocks

| Reason | Fix |
|---|---|
| `fidelity F0 < target F3` | the higher checks are stubbed/failing; implement until they pass |
| `projection/fidelity drifted` | you edited a pinned field — revert it |
| `independence audit failed` | you read Sail or cribbed the machine model — remove it |
| `reasoning-side differential trust failed` | declare >=2 unrelated solvers; ensure they agree |
| `machine_tool ... not gated GREEN` | the group's btor2-machine isn't verified yet; either wait for the machine-build agent or don't rely on the `machine` path |

## The golden rule

The gate, on a clean checkout, is the only verdict. Your local runs are
feedback. Do not try to influence the gate — you cannot, and the attempt
fails the independence audit.
