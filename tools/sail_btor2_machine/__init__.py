"""The generic ``sail -> btor2`` machine tool.

ISA-agnostic. Turns a Sail ISA model into a BTOR2 *machine model* (a
universal CPU transition system) whose whole-machine equivalence to Sail is
proven once, then publishes it as a realization of that ISA's semantics
group. A program "translates" by initialization (load memory + PC).

This is a *generator*, not a subject-program pair: it consumes one fixed
artifact (the Sail model) and produces one fixed artifact (the machine
model). Invoke it per ISA (rv64 now; aarch64/x86/CHERI later, unchanged).
"""

from gurdy.hops.base import NotYetImplemented  # noqa: F401
