"""Convert a C corpus task into a CBMC-friendly C source.

The C corpus uses bare-metal idioms CBMC can't process directly
(``void _start(void)``, an ``ebreak`` halt, a ``noreturn`` ``trap``,
register-asm symbolic inputs), and reaches the "trap reachable" property
several ways across the two task families (a literal ``if (cond) trap();``
in the hand-written tasks; the ``reach_error``/``abort``/``__VERIFIER_assert``
macros and a ``goto ERROR`` idiom in the svcomp-extracted tasks).

The rewrite is now the single implementation in the ``c-riscv`` hop —
``gurdy.hops.c_riscv.to_cbmc_dialect`` — which rewrites the ``trap``
*definition* into a ``__CPROVER_assert(0, "trap reachable")`` so every path
to ``trap`` becomes a CBMC assertion failure, regardless of call shape. This
module just applies it and writes the file, so the bench's ``task.cbmc.c``
can never drift from the hop's differential dialect. (The earlier in-script
regex pipeline only handled the hand-written ``if (cond) trap()`` shape — its
condition class excluded parens — so it silently mis-rewrote every
svcomp-extracted task.)

Verdict mapping when the bench's ``expected_verdict`` is consulted:

  CBMC ``VERIFICATION SUCCESSFUL`` ⇔ trap unreachable
  CBMC ``VERIFICATION FAILED``     ⇔ trap reachable

NB callers that *run* CBMC on the output should pass
``--no-unwinding-assertions`` (with ``--unwind N``) to match the bench's
bounded-reachability question; otherwise a non-terminating loop (svcomp
``while(1)`` tasks) yields a spurious FAILED from the unwinding assertion.
See ``gurdy/hops/c_riscv/verify.py:cbmc_verify``.

This script is invoked by ``condition_d_reference.py`` for the
§3.D smoke test, and by future ``tool_cbmc`` for the LLM-D-mode sweep.

Usage:
    python bench/riscv-btor2/corpus/_emit_cbmc.py <task_dir>

Writes ``<task_dir>/task.cbmc.c``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Single source of truth for the dialect (see module docstring).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from gurdy.hops.c_riscv import to_cbmc_dialect  # noqa: E402


def rewrite(src: str) -> str:
    return to_cbmc_dialect(src)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("task_dir", type=Path)
    p.add_argument(
        "--stdout", action="store_true",
        help="print to stdout instead of writing task.cbmc.c",
    )
    args = p.parse_args(argv)

    task_dir = args.task_dir.resolve()
    src_path = task_dir / "task.c"
    if not src_path.exists():
        print(f"no task.c in {task_dir}", file=sys.stderr)
        return 2
    rewritten = rewrite(src_path.read_text())
    if args.stdout:
        sys.stdout.write(rewritten)
        return 0
    out_path = task_dir / "task.cbmc.c"
    out_path.write_text(rewritten)
    print(f"  wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
