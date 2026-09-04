# kernel/second — the second lineage of the kernel's pure half

Lineage tag: **`kernel-second-g1`**. The first kernel (`kernel/*.py`) is
lineage **`kernel-first-g1`**. The two share no source and no descent;
their value is that they corroborate each other by byte-agreement on
`base`, `report`, and `graph`.

```
python3 -m kernel.second.driver base   [--registry DIR]
python3 -m kernel.second.driver report <run-dir> [--registry DIR]
python3 -m kernel.second.driver graph  <run-dir> [--registry DIR]
```

`report` and `graph` print to stdout and write nothing. Stdlib only,
Python 3.11+, deterministic; nothing under this package imports any
other `kernel.*` module or reads any file under `kernel/` at runtime.

## The clean-room protocol followed

Nothing under `kernel/` outside this directory was read, displayed,
imported, introspected, or shown through git — no `kernel/*.py`, no
`kernel/mechanization/*`, no `kernel/tests/*`, no bytecode. The first
kernel was run only as a black box through its CLI. One disclosure: an
early black-box run of the first kernel on a registry copy with a
duplicated entry ended in a Python traceback on stderr that named
`kernel/driver.py` and `kernel/registry.py` with line numbers, one call
expression, and the exception text; no source file was opened. The
first kernel's CLI has since been changed to refuse a corrupt registry
with `refused: ...` on stderr and exit 1 rather than a traceback, so no
source line leaks through the black box any more.

Read (2026-09-04, working tree of `main`):

- `KERNEL.md` (whole; §5 and §10 re-read after their 2026-09-04
  pinning), `README.md` (whole), `HISTORY.md` (whole); `POTENTIAL.md`
  was not needed and not read.
- `registry/*/*/manifest.json` — all 25 admitted entries (the long
  `notes` strings of language and search manifests were truncated for
  display; nothing else of any entry was read beyond the bytes the §10
  pin hashes).
- `runs/*/benchmark.json`, `runs/*/log.jsonl` (record shapes, field
  distributions, ledger fields), `runs/*/frontier.md`,
  `runs/*/frontier.dot` — all four runs.
- The synthetic corner run the suite generates (fourteen one-line C
  programs, a 30-record log), the first kernel's board and graph on it
  (`first.md` / `first.dot`), and its base on a two-domain registry
  copy (`first-two-base.txt`).
- Directory listings (`ls`, `find`, `wc`) of `registry/`, `runs/`, and
  the names of files under `kernel/`.

Run: `python3 -m kernel.driver base` (on `registry/`, on an empty
directory, on a registry copy with a duplicated entry), and
`python3 -m kernel.driver report|graph` on the four runs and the corner
run (stdout captured as the reference; equal to the committed files and
to `first.md`/`first.dot`). Never `play`, `admit`, or `regrade`. Git was
used read-only (`git branch --show-current`, `git status --short`,
`git check-ignore`).

## Acceptance (all pass)

- `base` byte-identical to the first kernel's, on `registry/`, on an
  empty registry directory, and on a registry where one language is
  anchored by two domains.
- `report` and `graph` byte-identical to the first kernel's stdout and to
  the committed `frontier.md` / `frontier.dot` for `hwmcc24-mini`,
  `svcomp25-mini`, `hwmcc24-arrays`, `hwmcc24-mid`, and to
  `first.md` / `first.dot` on the fourteen-question corner run.
- A flipped byte in a vectors file of an admitted entry, a stamp with its
  `tree` removed, a corrupted pinned program in a benchmark copy, and two
  entries claiming one name at one revision each exit 1 with a message on
  stderr (the first kernel exits 1 on the same inputs).
- Two runs of every command produce identical bytes.
- No `import kernel` / `from kernel` / escaping relative import. A
  runtime audit hook (`sys.addaudithook` on `open`) run over `base`,
  `report`, and `graph` sees exactly one file under `kernel/` outside
  `kernel/second/`: the bytecode of the `kernel` package's own
  `__init__`, loaded by Python's import system because `kernel.second` is
  a subpackage of `kernel` — not read by any module here — and nothing
  else; `sys.modules` afterwards holds only `kernel` and
  `kernel.second.*`.

## Fixed by the specification

- The pin (§10): sha256 over sorted-keys JSON, separators `, ` and `: `,
  of `{entry-relative path: sha256}` over every regular file except the
  top-level `manifest.json`, dotfiles, `__pycache__`, `.pyc`. Verified on
  all 25 stamps; a mismatch or a missing `tree` is a hard error.
- Admission = the presence of an `admission` stamp; a name binds to its
  highest admitted revision and to exactly one entry per revision — two
  entries claiming the same name at the same revision are a hard error;
  revisions are sibling entries `<name>@<r>`.
- Benchmarks pin every program by sha256; a violation is a hard error.
- The order key `(level, bound, grade, gap)` with "latest wins among
  equal keys"; level 0/1/2; `inf` above every number; a witness above
  `inf` itself; a partial's bound is `progress.bound_reached`, none below
  zero; grades ungraded < claimed < checked < certified; a smaller gap
  better and no gap below every finite gap. Settled = level 2; the
  frontier = questions whose best is not settled, unplayed included.
- A result = a record with a `value` and a `question` of the benchmark;
  event records (`event`, including a recorded `contradiction` event) are
  not results — contradictions are recomputed from the results.
- Contradiction events (a witness at depth d beside a claim covering d)
  and the corroborated flag (two settled results of the best's kind with
  disjoint recorded `lineage` sets) as §4 states them.

## Inferred from outputs alone

From the four runs: every textual detail of board, graph, and base —
headers, the seven board columns, `—` for a null gap, `trust` as the
record's stored list joined by spaces, `route` as the list joined by
`>`, question rows in plain string order (`open1, open10, open2`), the
unplayed row `| q | — unplayed | | | | | |`, the frontier list with
`json.dumps(value, sort_keys=True)`, the ledger section and its rule
(S = the largest `S_bits_min`, `%.1f`; B = the largest `B_bits` with
`inf` highest, ties broken by the smallest `spent_s`; rate
`round(B/spent)`, `∞` at `inf`; the section omitted when no question has
a row), the graph (languages sorted, `peripheries=2` and the
`N questions, K open` label on languages holding questions; pairs sorted
by id with channels in manifest order and `(count)` of best paths;
searches as `search:<name>` doubleoctagons; edge style dotted when
unused, solid when used, bold when used and every question through it is
settled), and the base (interpreters sorted, labelled by entry directory
name, vectors and controls from the stamp, `lineage` as a Python list
repr, judges from `admission.evidence` sorted by schema, anchors from
`admission.anchors`).

From the corner run: a partial as best shows `partial (<note>)` when
`progress.note` is present (printed raw, non-ASCII included) and plain
`partial` otherwise (never its bound), an empty grade cell, `—` for the
gap, and its frontier line dumps `progress` alone (sorted keys,
`json.dumps` defaults, so non-ASCII is `\u`-escaped there) while a
non-partial dumps the whole value; an empty stored `trust` list prints
`judge only` on a graded result and `—` on an ungraded one; `spent_s`
prints verbatim when an int, through `%.1f` when a float, and as an
empty cell when the budget is missing; a non-integral `B_bits` prints its
decimals (`96.5`), and a winning record with `spent_s` = 0 prints `—` for
the rate; the corroborated flag is ` +corroborated` appended to the grade
cell, earned by any two settled results of the best's kind (the best need
not be one of them) and never by a record whose `lineage` is missing or
empty; the contradictions section is `## Contradictions (chain
falsified)`, at the very end of the board after the ledger, one bullet
per witness/universal pair whose bound covers the depth — universals in
log order, a numeric bound as `to bound 10`, `inf` as `to bound inf` —
showing the universal's route; an empty registry prints `(empty: zero
admitted judges — the kernel ships this way)` between the header and the
trailer; a language anchored by several domains lists them
comma-separated in domain-name order, each as `<domain> (<n> anchors)`.

## Ambiguities and possible divergence on inputs not yet exercised

1. **Partial without a `progress` object**: cell `partial`, frontier line
   `{}`; an empty-string note prints plain `partial`.
2. **Contradiction bullets** with several witnesses on one question: the
   order here is witnesses in log order, universals in log order within
   each; only one witness per question has been verified.
3. **Ledger edge cases**: equal `spent_s` among equal B keeps the first
   record; a missing `spent_s` on the winning record prints `—` and
   sorts last in the tie-break; the section is omitted on "no rows" (the
   first kernel might key on an empty log); `round` is banker's rounding
   (matched all rows; truncation does not).
4. **`spent_s` of another type** (a string, a bool) prints via `str()`
   / as empty.
5. **Route**: a string route prints verbatim; an empty list prints an
   empty cell and draws nothing; a hop naming an entry absent from the
   registry counts on the board but draws no edge.
6. **Benchmark name** is `benchmark.json`'s `name`, not the directory
   name (they coincide in every run seen).
7. **Registry corner cases**: name from `name`/`id` (fallback: the
   directory name before `@`); revision from `revision` (fallback: the
   `@r` suffix, else 1) — so a `riscv@1` directory beside `riscv` counts
   as the same revision here; an `admission` that is not an object, or a
   manifest that is not valid JSON, is a hard error; dot-directories are
   excluded from the pin along with dotfiles; symlinked directories are
   not followed.
8. **Base**: anchors fall back to `len(anchors)` when the stamp has no
   count.
9. **Graph**: the languages drawn with `peripheries=2` are those named
   by a benchmark question's own `language` (the first kernel may use
   the domain's root); counts are over best paths, unplayed excluded.
10. Unknown grade strings rank as ungraded (and, being non-empty, print
    `judge only` on an empty trust list); a boolean `gap` counts as
    absent; a `value` that is not an object is not a result; a `kind`
    outside witness/all/partial is treated as a partial.
11. `report` and `graph` load (and so verify) the registry although
    today's board draws nothing from it; a corrupt registry therefore
    fails them as well as `base`.
