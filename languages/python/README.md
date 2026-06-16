# Language — Python

A defined **subset** of Python, as a high-level source language. Source of
the `python-smtlib` pair — which is an **open candidate**
([`pairs/python-smtlib`](../../pairs/python-smtlib/README.md)): whether
Python is the right next high-level source, and which subset, is undecided.
This brief records the language so the candidate is concrete.

## Formal semantics (source of truth)

Python's reference semantics is the CPython language reference, which is
informal and large; a pair must therefore fix a **subset** with a precise
small-step semantics (integers, booleans, basic containers, functions,
bounded loops — the exact set is the pair's to declare). Within that subset
the meaning is a definable transition over an environment/heap.

## Formal model — no Sail, use a mechanized Python semantics

Not an ISA — no Sail. The mechanized references are:

- **K-Python** — Dwight Guth's Python 3.3 semantics in the **K framework**,
  tested against CPython (an interpreter + analysis tools). The recommended
  gold oracle for a defined subset.
- A recent **structural operational semantics** for Python (executable),
  usable as a second reference.

For the chosen subset, K-Python (restricted accordingly) or a purpose-built
small-step subset semantics is the oracle for the shared interpreter.

## Shared interpreter

**Role: source.** A deterministic executor of the chosen subset over an
input binding → a trace of post-step program states
([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5). Because a full Python
interpreter is large, the pair may **re-execute against the real
interpreter** restricted to the subset rather than mirror it — the soundness
trade-off [`PAIRING.md`](../../PAIRING.md) §6/§9 flags for high-level
languages. Shared by every Python pair.

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): the **CPython
test suite**, restricted to the chosen subset and pinned to a CPython tag,
with K-Python as the differential oracle. (Deferred with the pair itself —
this is a candidate, open.)

## Pairs over this language

- [`python-smtlib`](../../pairs/python-smtlib/README.md) — source (candidate, open).
