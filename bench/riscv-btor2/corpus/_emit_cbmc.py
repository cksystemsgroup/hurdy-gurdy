"""Convert a v0.4 C task into a CBMC-friendly C source.

The v0.4 C corpus uses bare-metal idioms that CBMC can't process
directly:

  - ``void _start(void)`` instead of ``int main(void)``
  - ``__asm__ volatile ("ebreak")`` to halt
  - ``if (cond) trap();`` for assertions, where ``trap()`` is a
    separate function ending in another ``ebreak``
  - ``extern void trap(void) __attribute__((noreturn));``

This rewriter converts each task into the CBMC dialect:

  - rename ``void _start(void)`` → ``int main(void)``
  - rewrite ``if (cond) trap();`` →
    ``__CPROVER_assert(!(cond), "trap reachable");``
  - strip ``__asm__`` lines (CBMC silently no-ops them anyway,
    but stripping makes the generated source readable)
  - drop the ``extern`` declaration of ``trap`` and its
    definition (no callers remain after the rewrite)

Verdict mapping when the bench's `expected_verdict` is consulted:

  CBMC ``VERIFICATION SUCCESSFUL`` ⇔ trap unreachable
  CBMC ``VERIFICATION FAILED``     ⇔ trap reachable

This script is invoked by ``condition_d_reference.py`` for the
§3.D smoke test, and by future ``tool_cbmc`` for the LLM-D-mode
sweep.

Usage:
    python bench/riscv-btor2/corpus/_emit_cbmc.py <task_dir>

Writes ``<task_dir>/task.cbmc.c``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# --- Regex rules ------------------------------------------------------------
#
# Each rewrite rule is (regex, replacement). Order matters: stripping the
# trap definition first keeps the trap-call rewrite from accidentally
# touching the function body.

_RULES: tuple[tuple[re.Pattern, str], ...] = (
    # Drop `extern void trap(void) __attribute__((noreturn));` line.
    (re.compile(r"^extern void trap\([^)]*\)[^;]*;\s*$", re.MULTILINE), ""),

    # Drop the entire `void trap(void) { ... }` function definition.
    # Non-greedy match against the body; assumes single-line body or
    # a simple multi-line body without nested braces (true for our
    # corpus).
    (re.compile(
        r"^void trap\(void\)\s*\{[^}]*\}\s*$",
        re.MULTILINE | re.DOTALL,
    ), ""),

    # Rename _start to main.
    (re.compile(r"void _start\(void\)"), "int main(void)"),

    # Rewrite `if (cond) trap();` → __CPROVER_assert(!(cond), ...).
    # The condition is anything between the if's parens; we use a
    # balanced-parens regex via [^()]* (corpus tasks have no nested
    # parens in conditions, true today; revisit if a task changes).
    (re.compile(r"if\s*\(([^()]+)\)\s*trap\(\)\s*;"),
     r'__CPROVER_assert(!(\1), "trap reachable");'),

    # Strip `__asm__ volatile ("ebreak");` lines (and any other
    # __asm__ statement). CBMC silently no-ops them, but stripping
    # makes the rewritten source easy to read.
    (re.compile(r"__asm__\s+volatile\s*\([^)]*\)\s*;"), ""),

    # Strip `__builtin_unreachable();` (no-op for CBMC; cosmetic).
    (re.compile(r"__builtin_unreachable\(\)\s*;"), ""),
)


def rewrite(src: str) -> str:
    out = src
    for pat, repl in _RULES:
        out = pat.sub(repl, out)
    # Collapse runs of blank lines for readability.
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


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
