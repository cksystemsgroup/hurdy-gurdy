"""The generic commuting-square oracle (FRAMEWORK.md §2; ARCHITECTURE.md §3).

Walks the source behavior ``I_s(p)`` against the carried-back target behavior
``L(I_t(T(p)))`` step-by-step, under the pair's projection ``π``. A divergence
is localized to a (step, observable) — the property that lets a translation
bug point at itself.
"""

from __future__ import annotations

from .types import AlignResult, Divergence, Projection, Trace


def align(left: Trace, right: Trace, projection: Projection) -> AlignResult:
    """Check that two behaviors agree under ``projection``.

    ``left`` is the source-interpreted trace; ``right`` is the
    translate-interpret-carry-back trace. Returns ``ok`` or the first
    divergence.
    """
    if len(left) != len(right):
        return AlignResult(
            ok=False,
            divergence=Divergence(
                step=min(len(left), len(right)),
                field="<length>",
                left=len(left),
                right=len(right),
            ),
        )
    for step, (ls, rs) in enumerate(zip(left, right)):
        lp, rp = projection.select(ls), projection.select(rs)
        for fieldname in projection.fields:
            if lp.get(fieldname) != rp.get(fieldname):
                return AlignResult(
                    ok=False,
                    divergence=Divergence(
                        step=step,
                        field=fieldname,
                        left=lp.get(fieldname),
                        right=rp.get(fieldname),
                    ),
                )
    return AlignResult(ok=True)
