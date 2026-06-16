"""Typed errors shared by interpreters and translators.

The ``Unsupported`` abort is the honest-failure mechanism (BENCHMARKS.md §3):
an unsupported construct hard-aborts here, naming the construct, rather than
being silently dropped or mis-handled. The named construct is what the
coverage harness turns into the ``unsupported`` histogram.
"""

from __future__ import annotations


class Unsupported(Exception):
    """A construct outside the deliverable's declared scope.

    Always carry the construct name, e.g. ``Unsupported("riscv", "fence.i")``.
    """

    def __init__(self, language: str, construct: str, detail: str = "") -> None:
        self.language = language
        self.construct = construct
        self.detail = detail
        msg = f"unsupported: {language}:{construct}"
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)
