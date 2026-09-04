"""The kernel's own tests (KERNEL.md §9) — generated, like the kernel.

The kernel is the one piece of code the gate cannot judge, so it is
falsified the way everything else is. This package holds the
operational half of that discipline (the mathematical half is the
Lean development under ``kernel/mechanization/``):

- ``test_order``      — the result order, checked against the model
                        the Lean file proves: strict; the ratchet;
                        once settled, always settled; at a fixed
                        level and bound, grades only move up and the
                        gap never grows; ties go to the latest.
- ``test_registry``   — the append-only registry: the content pin as
                        KERNEL.md §10 defines it, re-verified on load;
                        changed bytes and pinless stamps refused;
                        names bind to the highest admitted revision.
- ``test_seal``       — the sealed runner: empty environment, scratch
                        working directory, wall cap, determinism
                        measured twice.
- ``test_gate``       — the gate run against the registry's own
                        controls: every bound entry's stamp is
                        re-derived by re-running its admission, every
                        supplied mutant refused; and on a toy registry
                        built from empty, every way of failing the
                        gate fails it.
- ``test_forge``      — the kernel cannot forge a result: on the toy
                        registry, a lying search, a broken carry-back,
                        a bogus certificate, and a route missing a
                        channel each lose a grade and never gain one;
                        ``regrade`` lifts a stored proof to certified
                        by check time alone.
- ``test_regenerate`` — the board and the graph of every pinned run
                        regenerate byte-identically from the log.
- ``test_second``     — the second lineage of the kernel
                        (``kernel/second/``) agrees byte-for-byte
                        with this one on the base, the board, and the
                        graph, and shares no source with it.

Run the fast tier (well under two minutes) with::

    python3 -m kernel.tests

and everything — every admitted entry of every kind re-gated, old
revisions included, which re-runs the searches and takes long — with::

    HG_SLOW=1 python3 -m kernel.tests
"""
