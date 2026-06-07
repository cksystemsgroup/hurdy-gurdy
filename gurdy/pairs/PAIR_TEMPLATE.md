# Pair scaffold — the registration shape every reasoning pair produces

*Stage 7.D (recorded 2026-06-07). The **code-shape** counterpart to
[`PAIRING.md`](../../PAIRING.md) (concepts) and
[`DESIGN_pair_taxonomy.md`](../../DESIGN_pair_taxonomy.md) (vocabulary). The
authoritative reference implementation is
[`riscv_btor2/__init__.py`](./riscv_btor2/__init__.py); read it alongside this
note. This exists because the four `*-btor2-bootstrap` branches each grew a
**different** internal layout and a different (often stale) registration; this
is the single shape they converge onto as they land (Stage 7.E).*

## 1. What a pair's `__init__.py` must do

Importing the package builds one `Pair` record and registers it, plus its two
languages:

```python
from gurdy.core.pair import LayerSpec, Pair, Preservation, Tier, register_pair
from gurdy.core.language import Language, register_language

PAIR = Pair( ... )            # see §2
register_pair(PAIR)
register_language(Language(id=<in_lang>,  kind="representation", semantics=...))
register_language(Language(id=<out_lang>, kind="reasoning", semantics=...,
                           reasons_via=tuple(sorted(PAIR.solvers))))
```

## 2. The `Pair` field contract

`Pair` is the solver-terminating species of `Hop` (`gurdy/core/hop.py`); it
inherits the Hop fields and adds the reasoning-pair machinery.

**Required (construction fails without them):**

| Field | What | riscv reference |
|---|---|---|
| `identifier` | the pair id | `"riscv-btor2"` |
| `schema_version` | `SCHEMA.md` version, semver | `_SCHEMA_VERSION` |
| `source_loader` | `payload -> source` | `load_riscv_binary` |
| `spec_class` | `BaseSpec` subclass | `RiscvBtor2Spec` |
| `spec_validator` | validates a spec | `validate_riscv_btor2_spec` |
| `layer_specs` | `tuple[LayerSpec, ...]` matching `SCHEMA.md` + `translation/layers` | `RISCV_BTOR2_LAYERS` |
| `translator` | `(spec, source, emitter) -> CompiledArtifact` (the Hop `compile` edge is derived from this) | `translate` |
| `lifter` | raw solver output → source-grounded facts | `lift` |
| `solvers` | `{name: SolverBackend}` | z3-bmc/z3-spacer/bitwuzla/cvc5/pono(+docker) |
| `schema_path` | `Path(__file__).parent / "SCHEMA.md"` | ✓ |

**Default-valued, but a hub pair MUST set them** (they default only so the
dataclass can construct; omitting them silently disables real capabilities):

| Field | Default | If omitted you lose… | riscv reference |
|---|---|---|---|
| `in_lang` | `""` | **routing** — `routes()`/chains can't see the pair | `"rv64-elf"` |
| `out_lang` | `""` | **routing** + the hub edge | `"btor2"` |
| `tier` | `Tier.transparent` | correct chain-trust meet | `Tier.transparent` |
| `preservation` | empty | `Route.discards` / `gurdy preservation` | `Preservation(keeps=…, discards=…, note=…)` |
| `source_interpreter` | `None` | the **alignment oracle** (no source trace) | `RiscvSourceInterpreter()` |
| `reasoning_interpreter` | `None` | alignment + reasoning-side trace | `Btor2ReasoningInterpreter()` |
| `projection` | `None` | **alignment + hub cross-check** (7.F) | `_projection_factory_for_artifact` |
| `witness_replayer` | `None` | grounding `reachable` witnesses | `replay_witness` |
| `predicate_evaluator` | `None` | the `check` tool | `evaluate_spec` |
| `interpreter_version` | `""` | provenance | `_INTERPRETER_VERSION` |

**The `projection` factory** is the one piece of non-boilerplate wiring. Mirror
the riscv pattern: parse the flattened BTOR2 once, build a `state symbol → nid`
table, close over it with `make_projection`:

```python
def _projection_factory_for_artifact(artifact):
    from gurdy.core.btor2.parser import from_text
    parsed = from_text(artifact.flattened.decode("utf-8", "replace"))
    sym_to_nid = {n.symbol: n.nid for n in parsed.model.nodes()
                  if n.op == "state" and n.symbol}
    return make_projection(sym_to_nid)
```

## 3. BTOR2 is shared — never re-implement it

The BTOR2 IR (model/parser/printer/evaluator) lives in **`gurdy.core.btor2`**
(Stage 7.B). A BTOR2-emitting pair imports it; it does **not** carry its own
`btor2/` package. Concretely:

- ✅ `from gurdy.core.btor2.parser import from_text`
- ✅ `from gurdy.core.btor2.nodes import Model, BitvecSort, ArraySort, Comment`
- ✅ `from gurdy.core.btor2.printer import to_text`
- ✅ `from gurdy.core.btor2.evaluator import evaluate`
- ❌ a private `gurdy/pairs/<x>_btor2/btor2/` clone (evm's branch has one — delete it on landing)

Keep the IR **width-parametric** (`BitvecSort(width)`) — EVM needs 256-bit.

The z3 BMC compiler (`solvers/_bmc.py`) is still pair-local on `main` (Stage
7.C is deferred until a landing pair's solvers want a shared path). For now a
new pair may keep its own `solvers/_bmc.py`; when 7.C lands, switch to the core
one.

## 4. The irreducible six (`PAIRING.md` §3) → where each lands

`source/` (loader + decoder) · `SCHEMA.md` · `spec.py` (spec vocabulary) ·
`translation/` (the translator → `layer_specs`) · `lift/` (the lifter +
replayer) · `solvers/` (SolverBackend wrappers). Plus `source_interp/`
(interpreter + **projection** + **predicates**) and `reasoning_interp/`, which
back the alignment oracle and the `check` tool.

## 5. Landing checklist (use when bringing a `*-btor2-bootstrap` pair onto `main`)

1. **Import the IR from `gurdy.core.btor2`** — rename any
   `gurdy.pairs.riscv_btor2.btor2.*` (the bootstrap branches predate 7.B) and
   delete any private `btor2/` clone.
2. **Modernize the `Pair` record** to §2: add `in_lang`/`out_lang`, `tier`,
   `preservation`, and wire every callable that exists
   (`source_interpreter`, `projection`, `witness_replayer`,
   `predicate_evaluator`). If `projection`/`predicates` don't exist yet, the
   pair lands as **registers + compiles** but **not cross-checkable** — note
   the gap explicitly; it is real follow-up, not done.
3. **`register_language`** for both `in_lang` and `out_lang`.
4. **Package `SCHEMA.md`** (the bootstrap branches added the `package-data`
   entry; keep it).
5. **Tests green** — the pair's own unit suite, RAM-safe (one pair at a time;
   skip Docker/solver-portfolio in routine runs).
6. **Hub cross-check** — once `projection` exists, a verdict cross-check
   against an existing pair through `btor2-smtlib` (Stage 7.F).

> Steps 1–5 are the *mechanical* land; step 6 (and the `projection`/`predicates`
> it needs) is the *cross-checkable* land. Don't conflate them.
