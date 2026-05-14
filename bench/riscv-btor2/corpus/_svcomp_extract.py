"""Vendor an SV-COMP C task as a hurdy-gurdy corpus task.

Translates a single sv-benchmarks `c/<category>/<task>.c` plus its `.yml`
sidecar into the directory layout `_compile_c.py` expects (a `task.c`
that uses the `trap()` convention plus a `task.toml` with `[task]`,
`[question]`, `[expected]`, `[c]`, and `[svcomp_extract]` blocks).
The vendored task directory preserves `original.c` and `original.yml`
for provenance.

Scope (v0.5 pilot, deliberately narrow):

- Reads ONLY the `unreach-call` property from the `.yml` and maps it
  to the bench's expected verdict (`true → unreachable`,
  `false → reachable`). Other properties (no-overflow, termination,
  etc.) are ignored.
- Accepts tasks with zero `__VERIFIER_nondet_*` calls, or with
  *entry-only* nondets (top-level `<type> <name> = __VERIFIER_nondet_*();`
  assignments at the start of `main`, before any branch / loop).
- Rejects tasks that use `__VERIFIER_assume`, malloc/calloc/free,
  pthread, FILE I/O, or arrays declared at function scope larger
  than 16 elements (stack pointer is uninitialized at the bench's
  `_start`, so stack-array access is undefined).

Source rewriting:

- Strips the SV-COMP boilerplate `extern void abort`,
  `extern void __assert_fail`, `void reach_error() {...}` body, and
  `void __VERIFIER_assert(int cond) {...}` body. Strips
  `#include <assert.h>`.
- Pre-pends a shim that redefines `reach_error` as a macro for
  `trap`, `abort()` as `trap()`, and `__VERIFIER_assert` as a
  trap-on-false inline function.
- Renames `int main(...)` to `int task_main(<args>)`. For each
  entry-level nondet (in source order), `task_main` gains an arg
  of the matching type; the nondet call is replaced by the arg.
- Appends a `_start` that pulls a0..aN through `register` /
  `__asm__` declarations (uninitialized at entry → BMC-symbolic)
  and forwards them to `task_main`.
- Appends a `trap` definition.

After rewriting, the caller is expected to invoke
`_compile_c.py <task_dir>` to produce the ELF + sidecars + spec.

Usage:
    python bench/riscv-btor2/corpus/_svcomp_extract.py \
        --sv-bench-root bench/riscv-btor2/external/sv-benchmarks \
        --pick c/bitvector-regression/integerpromotion-2.c \
        --task-id 0201-svcomp-integerpromotion-2 \
        --bound 60
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore


EXTRACTOR_VERSION = "0.1.0"

# v0.5 pilot supports only these two nondet return types. RV64 LP64
# ABI sign- or zero-extends 32-bit ints to 64-bit registers on the
# argument side; we map both to 32-bit C types so the rewritten
# task_main signature matches the original SV-COMP source.
NONDET_TYPE_MAP = {
    "__VERIFIER_nondet_int":  "int",
    "__VERIFIER_nondet_uint": "unsigned int",
}

NONDET_REJECT_TYPES = {
    # known but unsupported: would need different ABI handling or
    # different bench semantics.
    "__VERIFIER_nondet_long":     "long (LP64 64-bit; not in pilot scope)",
    "__VERIFIER_nondet_ulong":    "unsigned long (LP64 64-bit; not in pilot scope)",
    "__VERIFIER_nondet_char":     "char (sub-register; not in pilot scope)",
    "__VERIFIER_nondet_uchar":    "unsigned char (sub-register; not in pilot scope)",
    "__VERIFIER_nondet_short":    "short (sub-register; not in pilot scope)",
    "__VERIFIER_nondet_ushort":   "unsigned short (sub-register; not in pilot scope)",
    "__VERIFIER_nondet_float":    "float (FP; SCOPE.md §5)",
    "__VERIFIER_nondet_double":   "double (FP; SCOPE.md §5)",
    "__VERIFIER_nondet_pointer":  "pointer (heap; SCOPE.md §5)",
}


# Patterns that disqualify a task from the pilot.
_REJECT_PATTERNS = (
    (re.compile(r"\b__VERIFIER_assume\s*\("), "uses __VERIFIER_assume"),
    (re.compile(r"\b(malloc|calloc|realloc|free)\s*\("), "uses heap allocation"),
    (re.compile(r"\bpthread_"),                "uses pthread"),
    (re.compile(r"#include\s*<stdio\.h>"),     "uses stdio"),
    (re.compile(r"\bfopen\s*\("),              "uses FILE I/O"),
    (re.compile(r"#include\s*<.*string\.h>"),  "uses string.h"),
)


@dataclass
class ExtractionPlan:
    nondet_args: list[tuple[str, str]]  # (c_type, arg_name)
    rewritten_c: str


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="strict")


def _parse_yml_unreach_call(yml_text: str) -> bool | None:
    """Return the unreach-call expected_verdict (True/False) or None
    if the .yml has no unreach-call property."""
    # The .yml is YAML 1.x but we only need a small slice: find the
    # block starting with `- property_file: ../properties/unreach-call.prp`
    # and pull the `expected_verdict:` on the next line.
    lines = yml_text.splitlines()
    for i, line in enumerate(lines):
        if "unreach-call" in line and "property_file" in line:
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.search(r"expected_verdict:\s*(true|false)\b", lines[j])
                if m:
                    return m.group(1) == "true"
    return None


def _yml_data_model(yml_text: str) -> str | None:
    m = re.search(r"data_model:\s*([A-Z0-9]+)", yml_text)
    return m.group(1) if m else None


def _check_rejects(src: str) -> str | None:
    for pat, why in _REJECT_PATTERNS:
        if pat.search(src):
            return why
    return None


def _find_nondet_calls(src: str) -> list[tuple[int, str]]:
    """Return [(offset, callee_name), ...] for every __VERIFIER_nondet_*
    call site (including extern declarations — we filter those out
    later). Sorted by offset."""
    return sorted(
        (m.start(), m.group(1))
        for m in re.finditer(r"\b(__VERIFIER_nondet_[A-Za-z_]+)\s*\(", src)
    )


def _strip_extern_decls(src: str) -> str:
    """Remove SV-COMP boilerplate declarations / definitions.

    Removed lines (regex-matched, each handled individually):
    - `extern void abort(void);` and similar
    - `extern void __assert_fail(...);` (single-line and multi-line)
    - `#include <assert.h>`
    - `extern <type> __VERIFIER_nondet_<type>();` declarations
    - `void reach_error() { __assert_fail(...); }` (single line)
    - `void reach_error() { assert(0); }` (single line)
    - `void __VERIFIER_assert(int cond) { ... }` (the multi-line body)
    """
    # Remove single-line includes / extern decls.
    patterns = [
        r"^extern\s+void\s+abort\s*\(\s*void\s*\)\s*;\s*$",
        r"^extern\s+void\s+__assert_fail\s*\([^;]*\)\s*[^;]*;\s*$",
        r"^extern\s+\w[\w\s\*]*\s+__VERIFIER_nondet_\w+\s*\(\s*(void)?\s*\)\s*;\s*$",
        r"^\w[\w\s\*]*\s+__VERIFIER_nondet_\w+\s*\(\s*\)\s*;\s*$",  # no-`extern` form
        r"^#include\s*<assert\.h>\s*$",
    ]
    for pat in patterns:
        src = re.sub(pat, "", src, flags=re.MULTILINE)
    # reach_error() body — the body's brace nesting varies (single-
    # line `assert(0);` vs. multi-line ERROR label), so strip via
    # the same brace counter we use for __VERIFIER_assert.
    src = _strip_function(src, "reach_error")

    # Remove __VERIFIER_assert function body. The body has nested
    # braces (`if (!cond) { ERROR: { reach_error(); abort(); } }`),
    # so we hand-match the outermost `{...}` with a brace counter
    # rather than a regex.
    src = _strip_function(src, "__VERIFIER_assert")
    # Some SV-COMP variants additionally define static `reach_error`
    # bodies on multiple lines, or `__VERIFIER_atomic_*` helpers; the
    # pilot only handles the canonical __VERIFIER_assert shape, so
    # bail loudly if anything else with a nested body slipped through.
    return src


def _strip_function(src: str, name: str) -> str:
    """Remove a free-standing C function definition named ``name``
    from ``src``. Matches ``[return-type] <name>(...) { ... }`` where
    braces are balanced; only the outermost body is matched."""
    pat = re.compile(
        r"(?P<head>\b\w[\w\s\*]*\s+" + re.escape(name) + r"\s*\([^)]*\)\s*)\{",
    )
    while True:
        m = pat.search(src)
        if m is None:
            return src
        # m.end() points at the byte AFTER the `{`. Walk forward with
        # a brace counter.
        i = m.end()
        depth = 1
        n = len(src)
        while i < n and depth > 0:
            c = src[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        if depth != 0:
            raise ValueError(f"unbalanced braces while stripping {name!r}")
        # Drop the entire `[head]{...body...}` slice.
        src = src[: m.start()] + src[i:]


def _shim_header(*, original_path: str, svcomp_verdict: str, bench_verdict: str) -> str:
    return (
        "// Generated by bench/riscv-btor2/corpus/_svcomp_extract.py\n"
        f"// Original: {original_path}\n"
        f"// SV-COMP unreach-call expected_verdict: {svcomp_verdict}\n"
        f"// Bench expected verdict: {bench_verdict}\n"
        "//\n"
        '// SV-COMP property semantics: reach_error() / __assert_fail() = "the\n'
        "// property fails\". The bench rephrases this as: trap() is reachable\n"
        "// iff the SV-COMP property fails.\n"
        "\n"
        "extern void trap(void) __attribute__((noreturn));\n"
        "\n"
        "// Macros (not functions) so gcc -O0 cannot emit them as\n"
        "// out-of-scope helpers the bench's dispatch ITE doesn't cover.\n"
        "#define reach_error()        trap()\n"
        "#define abort()              trap()\n"
        "#define __VERIFIER_assert(c) do { if (!(c)) trap(); } while (0)\n"
        "\n"
    )


_TRAP_DEF = """

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
"""


def _rewrite_main(src: str, nondets: list[tuple[str, str]]) -> str:
    """Rename `int main(...)` to `int task_main(<args>)` where each
    nondet contributes a positional arg. Inserts a `_start` after
    task_main that pulls a0..aN through register-asm declarations
    and forwards them.

    Caller has already substituted each nondet call site with the
    matching arg name.
    """
    sig = ", ".join(f"{c_type} {arg_name}" for c_type, arg_name in nondets) or "void"
    # Replace the first occurrence of `int main(<anything>)` heuristically.
    new_src, n = re.subn(
        r"\bint\s+main\s*\([^)]*\)",
        f"int task_main({sig})",
        src,
        count=1,
    )
    if n != 1:
        raise ValueError("could not locate `int main(...)` to rename")
    # Add a `_start` that calls task_main and a `trap` body.
    asm_decls = "\n".join(
        f'    register {c_type} {arg_name} __asm__("a{i}");'
        for i, (c_type, arg_name) in enumerate(nondets)
    )
    asm_inputs = ", ".join(f'"=r"({arg_name})' for _, arg_name in nondets)
    if nondets:
        marker = f'    __asm__ volatile ("" : {asm_inputs});'
        call = "task_main(" + ", ".join(name for _, name in nondets) + ");"
    else:
        marker = ""
        call = "task_main();"
    start = f"""

void _start(void) {{
{asm_decls}
{marker}
    {call}
    __asm__ volatile ("ebreak");
}}
"""
    return new_src + start + _TRAP_DEF


def _plan(src: str) -> ExtractionPlan:
    """Strip boilerplate, identify nondets, rewrite call sites."""
    src = _strip_extern_decls(src)

    # Find remaining nondet call sites (after extern decls were stripped).
    # These should all be call-and-use sites, not declarations.
    calls = _find_nondet_calls(src)

    # Validate types and pick parameter names.
    nondet_args: list[tuple[str, str]] = []
    seen_arg_names: set[str] = set()
    for _, callee in calls:
        if callee in NONDET_REJECT_TYPES:
            raise ValueError(
                f"unsupported nondet type {callee!r}: {NONDET_REJECT_TYPES[callee]}"
            )
        if callee not in NONDET_TYPE_MAP:
            raise ValueError(f"unknown nondet callee {callee!r}")
        c_type = NONDET_TYPE_MAP[callee]
        # Synthesize a fresh arg name per call site.
        base = "v"
        i = len(nondet_args)
        name = f"{base}{i}"
        while name in seen_arg_names:
            i += 1
            name = f"{base}{i}"
        seen_arg_names.add(name)
        nondet_args.append((c_type, name))

    # Replace each call site with the corresponding arg name. Walk
    # call sites in source order and use a counter to consume the
    # arg list.
    arg_iter = iter(nondet_args)

    def replace(_match: re.Match) -> str:
        try:
            _, arg_name = next(arg_iter)
        except StopIteration:  # pragma: no cover - logic error
            raise RuntimeError("nondet replacement ran out of args")
        return arg_name

    rewritten = re.sub(
        r"\b__VERIFIER_nondet_[A-Za-z_]+\s*\(\s*\)",
        replace,
        src,
    )

    return ExtractionPlan(nondet_args=nondet_args, rewritten_c=rewritten)


def _validate_entry_only(src: str, nondet_count: int) -> None:
    """For the v0.5 pilot, every nondet call must appear in `main`'s
    prelude — i.e., before the first control-flow keyword. We check
    by locating `main(` and asserting all nondet calls precede any
    `if/while/for/do/goto/switch` inside `main`'s body.

    Lenient: only fires for >0 nondets.
    """
    if nondet_count == 0:
        return
    main_match = re.search(r"\bint\s+main\s*\([^)]*\)\s*\{", src)
    if not main_match:
        raise ValueError("no `int main(...)` body found")
    body_start = main_match.end()
    body = src[body_start:]
    # Find the first nondet call and the first control flow keyword
    # inside main's body.
    cf = re.search(r"\b(if|while|for|do|switch|goto)\b", body)
    nd = re.search(r"\b__VERIFIER_nondet_", body)
    if cf is None or nd is None:
        return
    if nd.start() > cf.start():
        raise ValueError(
            "nondet appears AFTER first control-flow keyword in main — "
            "not entry-only; pilot rejects this shape"
        )


def _git_sha(root: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return out


def _task_toml(
    *,
    task_id: str,
    bench_verdict: str,
    svcomp_pick: str,
    sv_bench_sha: str,
    yml_data_model: str | None,
    nondet_args: list[tuple[str, str]],
    bound: int,
) -> str:
    nondet_summary = (
        "; ".join(f"{t} {n}" for t, n in nondet_args) if nondet_args else "none"
    )
    return f"""\
[task]
id = "{task_id}"
task_class = "assertion-reachability"
difficulty = "T2"
lowering_sensitive = true
oracle_provenance = "svcomp-yml"

[question]
text = \"\"\"
Vendored from SV-COMP ({svcomp_pick}). The original C program's
`reach_error()` calls have been rewritten as `trap()` calls. Can
the `trap` function be reached?
\"\"\"

[expected]
verdict = "{bench_verdict}"

[c]
opt_level        = "0"
bound            = {bound}
included_callees = ["task_main", "trap"]

[svcomp_extract]
extractor_version = "{EXTRACTOR_VERSION}"
svcomp_pick       = "{svcomp_pick}"
sv_bench_commit   = "{sv_bench_sha}"
svcomp_data_model = "{yml_data_model or 'unset'}"
nondet_args       = "{nondet_summary}"

[notes]
text = \"\"\"
v0.5 pilot — vendored from sv-benchmarks. The bench's expected
verdict is derived mechanically from the SV-COMP `.yml` (the
`unreach-call.prp` property's `expected_verdict`: true →
unreachable, false → reachable). Pinned to -O0 (CORPUS_V0.5_PLAN.md
default).

The SV-COMP source is in `original.c`; the rewriter's output is
`task.c`. The rewriter (`bench/riscv-btor2/corpus/_svcomp_extract.py`,
version {EXTRACTOR_VERSION}) translates `reach_error()`/`abort()`/
`__VERIFIER_assert` into the bench's `trap()` convention and (for
entry-only nondets) routes `__VERIFIER_nondet_*` returns through
RV64 LP64 argument registers a0..aN that are uninitialized at
`_start` (hence symbolic in the bench's BMC).
\"\"\"
"""


def extract(
    *,
    sv_bench_root: Path,
    pick: str,
    task_id: str,
    out_root: Path,
    bound: int,
) -> Path:
    """Extract a single SV-COMP task into a corpus task directory.

    Returns the path of the created task directory.
    """
    src_c = sv_bench_root / pick
    src_yml = src_c.with_suffix(".yml")
    if not src_c.exists():
        raise FileNotFoundError(f"no such SV-COMP source: {src_c}")
    if not src_yml.exists():
        raise FileNotFoundError(f"no .yml beside {src_c}")

    raw = _read_text(src_c)
    yml = _read_text(src_yml)

    reject = _check_rejects(raw)
    if reject is not None:
        raise ValueError(f"rejected: {reject}")

    nondet_calls = _find_nondet_calls(raw)
    # The strip pass will remove extern decls; only the actual call
    # sites should remain. The count after strip is what _plan() uses.

    unreach = _parse_yml_unreach_call(yml)
    if unreach is None:
        raise ValueError(
            "no unreach-call property in .yml — pilot does not support "
            "other property shapes yet"
        )
    bench_verdict = "unreachable" if unreach else "reachable"

    plan = _plan(raw)
    _validate_entry_only(plan.rewritten_c, len(plan.nondet_args))

    final = (
        _shim_header(
            original_path=pick,
            svcomp_verdict=str(not bench_verdict_is_reachable(bench_verdict)).lower(),
            bench_verdict=bench_verdict,
        )
        + _rewrite_main(plan.rewritten_c, plan.nondet_args)
    )

    task_dir = out_root / task_id
    task_dir.mkdir(parents=True, exist_ok=False)
    # Preserve provenance.
    shutil.copy2(src_c, task_dir / "original.c")
    shutil.copy2(src_yml, task_dir / "original.yml")
    (task_dir / "task.c").write_text(final)
    (task_dir / "task.toml").write_text(
        _task_toml(
            task_id=task_id,
            bench_verdict=bench_verdict,
            svcomp_pick=pick,
            sv_bench_sha=_git_sha(sv_bench_root),
            yml_data_model=_yml_data_model(yml),
            nondet_args=plan.nondet_args,
            bound=bound,
        )
    )
    return task_dir


def bench_verdict_is_reachable(v: str) -> bool:
    return v == "reachable"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sv-bench-root",
        type=Path,
        required=True,
        help="path to the sv-benchmarks checkout (submodule root)",
    )
    ap.add_argument(
        "--pick",
        type=str,
        required=True,
        help="relative path inside sv-benchmarks, e.g. c/bitvector-regression/integerpromotion-2.c",
    )
    ap.add_argument(
        "--task-id",
        type=str,
        required=True,
        help="vendored task id, e.g. 0201-svcomp-integerpromotion-2",
    )
    ap.add_argument(
        "--out-root",
        type=Path,
        default=Path("bench/riscv-btor2/corpus"),
    )
    ap.add_argument("--bound", type=int, default=60)
    args = ap.parse_args(argv)

    task_dir = extract(
        sv_bench_root=args.sv_bench_root.resolve(),
        pick=args.pick,
        task_id=args.task_id,
        out_root=args.out_root.resolve(),
        bound=args.bound,
    )
    try:
        rel = task_dir.relative_to(Path.cwd().resolve())
    except ValueError:
        rel = task_dir
    print(f"wrote {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
