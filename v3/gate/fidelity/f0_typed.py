"""F0 — Typed. The one check that is *real* in this skeleton.

A hop passes F0 if it: imports cleanly, exposes a ``Hop`` with the manifest's
declared kind/in_lang/out_lang, declares its reasoning paths, and (if it
declares a ``machine_tool``) lists a ``machine`` path. No semantic claim —
just that the artifact is well-formed and wired to its contract.
"""

from __future__ import annotations

import importlib

from gurdy.core.manifest import Manifest
from gurdy.core.report import CheckResult, CheckStatus, Fidelity


def check(manifest: Manifest) -> CheckResult:
    modname = f"gurdy.hops.{manifest.id}"
    try:
        mod = importlib.import_module(modname)
    except Exception as e:  # noqa: BLE001
        return CheckResult(Fidelity.F0_typed, CheckStatus.FAIL, f"import {modname}: {e!r}")

    hop = getattr(mod, "HOP", None)
    if hop is None:
        return CheckResult(Fidelity.F0_typed, CheckStatus.FAIL, "no HOP exported")

    problems: list[str] = []
    if hop.kind != manifest.kind:
        problems.append(f"kind {hop.kind!r} != manifest {manifest.kind!r}")
    if hop.in_lang != manifest.in_lang.id:
        problems.append(f"in_lang {hop.in_lang!r} != {manifest.in_lang.id!r}")
    if hop.out_lang != manifest.out_lang.id:
        problems.append(f"out_lang {hop.out_lang!r} != {manifest.out_lang.id!r}")
    if manifest.machine_tool and "machine" not in hop.paths():
        problems.append("manifest declares machine_tool but hop has no 'machine' path")

    if problems:
        return CheckResult(Fidelity.F0_typed, CheckStatus.FAIL, "; ".join(problems))
    return CheckResult(
        Fidelity.F0_typed,
        CheckStatus.PASS,
        f"typed ok; kind={hop.kind} paths={hop.paths()}",
    )
