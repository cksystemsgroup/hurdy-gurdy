"""Fault injection — the gate and the grades measured against faults
they were not shipped with (KERNEL.md §4, §10).

Every admitted entry ships its own mutants, and the gate refuses them;
that says the controls can fail, not how much they see. This package
measures the rest. It takes the executables a name currently binds to,
writes source mutants of them (``mutate``) — one classical fault each,
sampled reproducibly — and puts every mutant where the intact file
stood, in a scratch copy of the entry; the registry and the pinned
runs are never written.

``gate`` asks where a fault dies. The mutated entry faces what an
entry of its kind faces at admission, in this order, and the first
refusal is recorded:

- ``own``         the kind gate on the entry's own vectors, corpus,
                  and controls
- ``revision``    conservativity: byte-agreement with the predecessor
                  on the predecessor's checkable surface
- ``dependents``  for a judge only — the admission of every bound pair
                  and search that runs it, re-run against the mutant:
                  the squares, replays, and discharges that
                  corroborate a judge after it entered

A mutant no tier refuses *survived*. For a transport that is the
design's free surface: what it writes still faces judges at play
time. For a judge it is the trusted base's exposure, and the number
this experiment exists to state. Each record says whether the mutated
lines were executed by any admission input at all (``cover``), so a
survivor nothing looked at is told apart from one the gate looked at
and passed.

``play`` asks what a fault can do once the gate is out of the way
(``play.py``): every sampled mutant of a transport is forced in and
played on questions whose answer is known, and each record the kernel
writes is held against the truth — the same, a loss, or wrong, and if
wrong at which grade and whether its residual blames the faulty
entry. Judges are not played: a judge is what a play trusts.

Run::

    python3 -m kernel.faults targets
    python3 -m kernel.faults gate <entry> <file>  [--n N] [--seed S]
    python3 -m kernel.faults gate languages|pairs|searches|all
    python3 -m kernel.faults play <entry> <file>  [--n N] [--seed S]
    python3 -m kernel.faults play pairs|searches|all
    python3 -m kernel.faults report [<results.jsonl> ...]

``<entry>`` is a registry path such as ``languages/c@5`` and ``<file>``
an executable inside it such as ``evidence/ranges/check.py``. Results
are appended to ``kernel/faults/results/<gate|play>-<kind>.jsonl``
(``--out`` elsewhere), one record per mutant; both experiments draw
the same sample for the same seed, so their records join on (entry,
file, node, alt), and a run that is interrupted resumes where it
stopped. Mutants run sealed like everything else, under a wall four
times the intact entry's longest run and a memory cap; a sealed run is
named by the bytes it reads and executed once per name while the
intact entry is exercised, so a mutant re-runs only what it changes.
"""
