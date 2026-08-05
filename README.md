# hurdy-gurdy

A platform on which an untrusted LLM provably accumulates checked
semantic artifacts. Formal languages and their translations, solvers
as translations into a language of results, every artifact admitted by
a gate that checks the work rather than the author — and a frontier,
per benchmark, made of exactly the results that are not yet terminal.

Three documents:

- [`KERNEL.md`](./KERNEL.md) — the design. Translation and solving as
  one kind of edge; results as the only currency; certification as
  Λ-then-check on both sides with a strict grade ladder; autonomous
  growth in which the LLM never writes a result — only the kernel
  does, by running checked code; and the conjecture order that is the
  vision's core discipline: semantics first — decision procedures,
  then translation, then languages.
- [`HISTORY.md`](./HISTORY.md) — how the system evolves: the eras,
  what each redesign removed and why, and where everything removed
  still lives.
- `paper/` — the citable records: the instrument paper (*Untrusted
  Authors, Trusted Answers*, arXiv v2 = tag `arxiv.2`) and the
  frontier paper (`paper/frontier/`), with the Lean mechanizations
  beside them.

## Layout

```
kernel/                the fixed, hand-written part: five stdlib-only
                       Python modules + its own Lean mechanization
registry/              generated content, append-only: languages and
                       pairs with manifests, admission evidence stamped
runs/<benchmark>/      pinned benchmark, append-only log, frontier
                       report (regenerates byte-identically)
paper/                 the papers and their mechanizations
gurdy/ pairs/ languages/ tools/   the Era-3 quarry: the previous
                       platform generation, kept in-tree as the source
                       the carry-over wraps into registry entries
tests/                 the whole suite — kernel tests and quarry tests
```

## Run

```sh
python3 -m unittest discover -s tests            # the full suite
python3 -m kernel.driver play runs/btor2-demo --wall 30
python3 -m kernel.driver report runs/btor2-demo  # pure log -> report
cd kernel/mechanization && lake build            # the kernel's proofs
```

The demo (`runs/btor2-demo/`) is the first kernel-played map: a
witness replayed through the shared interpreter, a bounded universal
terminal at *claimed*, and an unbounded ask honestly on the frontier —
the shape of everything the platform does, in three questions.

## Lineage

Hurdy-gurdy descends from rotor, originally developed as part of
selfie ([github.com/cksystemsteaching/selfie](https://github.com/cksystemsteaching/selfie),
`tools/rotor.c`); the full genealogy is [`HISTORY.md`](./HISTORY.md).

This work was co-funded by the Czech Science Foundation under Grant
No. 23-07580X and the European Union under the project Robotics and
Advanced Industrial Production (reg. no.
CZ.02.01.01/00/22_008/0004590).
