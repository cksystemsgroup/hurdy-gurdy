# Per-condition prompt templates

§9.3 instantiation. One file per condition the playbook actually
runs (A, B, C; D is omitted per `SCOPE.md` §6). The differences
across files are strictly the bullets in BENCHMARKING.md §9.3 — no
other variation. The harness substitutes `{{...}}` placeholders.

```
prompts/
├── README.md            # this file
├── _base.md             # shared sections: verdict vocabulary, output JSON
├── condition_a.md       # source + question + base
├── condition_b.md       # A + pair tool surface + SCHEMA.md reference
├── condition_c.md       # A + solver I/O reference + single solver tool
├── tools_b.json         # Anthropic tool schemas for compile/dispatch/lift/introspect
└── tools_c.json         # Anthropic tool schemas for the raw solver
```

## Placeholders

| Placeholder | Source | Conditions |
|---|---|---|
| `{{TASK_ID}}` | task.toml `[task.id]` | A, B, C |
| `{{QUESTION_TEXT}}` | task.toml `[question.text]` | A, B, C |
| `{{SOURCE_S}}` | `<task>/source.S` | A, B, C |
| `{{DISASSEMBLY}}` | `riscv64-unknown-elf-objdump -d source.elf` | A, B, C |
| `{{STARTER_SPEC_JSON}}` | the task's spec.json, *with property and witness fields stripped* — the LLM must derive those | B |
| `{{PAIR_ID}}` | `riscv-btor2` | B |
| `{{SCHEMA_URL}}` | URL to SCHEMA.md | B |

The full prompt for any condition is the result of `cat _base.md
condition_X.md | replace_placeholders`. Condition B/C also carry
their `tools_*.json` as the API's `tools` parameter.

## Vendor translation

`tools_b.json` and `tools_c.json` are written in Anthropic's tool
format (matching Slot A in `llms.md`). For Slot B (a non-Anthropic
family), the harness translates at runtime; the translation logic
lives in the harness, not here.

## Differences across conditions, exhaustively

| Section | A | B | C |
|---|---|---|---|
| Source program | shown | shown | shown |
| Question | shown | shown | shown |
| Output schema (`_base.md`) | shown | shown | shown |
| Pair tool surface | — | shown | — |
| `SCHEMA.md` link | — | shown | — |
| Starter spec.json | — | shown (property stripped) | — |
| Solver I/O reference | — | — | shown |
| Raw solver tool | — | — | shown |

Anything else introduced in B or C invalidates the §3 isolation
argument. PR reviewers should grep for additional asymmetries.

## Pre-registration

Per BENCHMARKING.md §7, every file in this directory must be in the
tagged commit before condition B/C runs. Edits to a prompt after
pre-registration mean re-running the affected cells.
