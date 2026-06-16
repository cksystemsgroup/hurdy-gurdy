# Pair — `python-smtlib`  ·  Python → SMT-LIB

*Status: **candidate (open)** — not registered for build. Carried over from
v2 as an open question.*

Compile a defined **subset** of Python to SMT-LIB. Whether Python is the
right next high-level source language — and which subset gives the fastest
signal — is **undecided**; this brief exists so the candidate is concrete,
not to trigger an agent yet. It is the platform's test of the hardest open
question in [`PAIRING.md`](../../PAIRING.md) §9: the soundness story for a
high-level language whose real interpreter is large.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** Python (a subset) —
  [`languages/python`](../../languages/python/README.md).
- **Target.** SMT-LIB — [`languages/smtlib`](../../languages/smtlib/README.md).
- **Translator `T`.** A schema-determined encoding of the chosen subset to
  SMT-LIB (the logic depends on the subset — `QF_LIA` / `QF_ABV` / arrays
  for containers). Deterministic.
- **Source interpreter.** The **shared** Python-subset interpreter
  ([`languages/python`](../../languages/python/README.md)) — likely **the
  real interpreter restricted to the subset**, not a mirror (the open
  soundness trade-off).
- **Target interpreter.** SMT-LIB's model evaluator + text I/O — reused.
- **Target-to-source interpreter `L`.** Decodes an SMT model into a
  Python-subset behavior (the inputs + the run exhibiting the property).
  Pair-owned.

## The open questions to resolve before building

- **Subset.** Which Python constructs are in scope, with what precise
  small-step semantics.
- **Soundness story** ([`PAIRING.md`](../../PAIRING.md) §6, §9). Mirror the
  encoding in a small interpreter, **re-execute against real CPython
  restricted to the subset**, or define soundness only at the property
  level? This choice is the reason the pair is deferred.
- **Gold oracle.** **K-Python** (Guth's Python 3.3 in the K framework,
  tested vs CPython), restricted to the subset, is the recommended reference
  ([`languages/python`](../../languages/python/README.md)).

## Fidelity target

- Aim `predicted` on the encoding; the harder claim is a credible soundness
  story for witness replay through a high-level interpreter — which is
  exactly what makes this a research question rather than a port.

## Notes

- Do **not** trigger a per-pair agent on this until the subset and soundness
  story are decided by a human ([`AGENTS.md`](../../AGENTS.md) §1, §5).
- Solvers/checkers are SMT-LIB's shared inventory ([`SOLVERS.md`](../../SOLVERS.md)).
