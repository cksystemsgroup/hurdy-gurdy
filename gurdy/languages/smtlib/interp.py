"""The shared SMT-LIB target interpreter ``I_t`` (ARCHITECTURE.md §5).

Runs *one* model through a script and reports whether it satisfies it — a
one-state ``Trace`` whose single observable ``sat`` is the deterministic
verdict for that model (the witness check of eval.py). It is the concrete
executor the language owns and shares; the *solver* (which searches over all
models) is the separate, quarantined oracle (SOLVERS.md §1, solvers/z3_smt.py).
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from .eval import evaluate


def interpret(artifact: Any, binding: dict[str, Any] | None = None, **_kw: Any) -> Trace:
    """``binding`` carries the model under ``"model"`` (or is itself the model);
    returns ``[{"sat": <does the model satisfy the script>}]``."""
    binding = binding or {}
    model = binding.get("model", binding) if isinstance(binding, dict) else {}
    return [{"sat": evaluate(artifact, model if isinstance(model, dict) else {})}]
