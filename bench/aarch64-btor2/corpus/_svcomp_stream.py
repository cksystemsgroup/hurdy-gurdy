"""Stream a single SV-COMP C file from GitHub and vendor it as an
aarch64-btor2 corpus task.

Unlike bench/riscv-btor2/corpus/_svcomp_extract.py (which needs a full
sv-benchmarks checkout), this module fetches exactly one .c + .yml pair
by raw GitHub URL — no local clone needed.

Each pick must appear in WHITELIST (a hardcoded frozenset of SV-COMP
relative paths).  The pinned sv-benchmarks commit is
2e1723fde6aa65a250dcb677efa45edaa4b6b631.

AArch64 adaptations vs. the riscv-btor2 extractor:
- Normal halt:    ``svc #0``   (RISC-V: ``ebreak``)
- Bad halt:       ``brk #0``   (RISC-V: ``ebreak``)
- Arg registers:  w0..w7       (RISC-V: a0..a7 / RV64 LP64)
- pair:           aarch64-btor2

After writing task.c + task.toml, the script attempts to compile via
_compile_c.py.  If aarch64-linux-gnu-gcc is absent the compile step is
skipped (dry-run) and a message is printed; spec.json is not emitted.

Usage::

    python bench/aarch64-btor2/corpus/_svcomp_stream.py \\
        --pick c/bitvector-regression/implicitunsignedconversion-1.c \\
        --task-id 0250-svcomp-implicit-uns-conv-1 \\
        [--out-root bench/aarch64-btor2/corpus/svcomp_slice] \\
        [--bound 60] \\
        [--dry-run]

Scope (pilot, deliberately narrow):

- ``unreach-call`` property only; other SV-COMP properties ignored.
- Accepts zero nondets, or entry-only ``__VERIFIER_nondet_int`` /
  ``__VERIFIER_nondet_uint`` calls (before any control-flow keyword).
- Rejects tasks that use ``__VERIFIER_assume``, heap allocation,
  pthread, stdio, or string.h.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

try:
    import tomllib  # py311+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

_HERE = Path(__file__).resolve().parent

EXTRACTOR_VERSION = "0.1.0"
_PINNED_COMMIT = "2e1723fde6aa65a250dcb677efa45edaa4b6b631"
_SV_RAW_BASE = (
    "https://raw.githubusercontent.com/sosy-lab/sv-benchmarks/"
    f"{_PINNED_COMMIT}/"
)
_MAX_FETCH_BYTES = 64 * 1024  # 64 KB — SV-COMP tasks are well below this

# Hardcoded set of allowed SV-COMP pick paths (relative to sv-benchmarks root).
# Mirrors the riscv-btor2 0250–0259 slice; new entries require code review.
WHITELIST: frozenset[str] = frozenset(
    {
        "c/bitvector-regression/implicitunsignedconversion-1.c",
        "c/bitvector-regression/implicitunsignedconversion-2.c",
        "c/bitvector-regression/integerpromotion-2.c",
        "c/bitvector-regression/integerpromotion-3.c",
        "c/bitvector-regression/signextension-1.c",
        "c/bitvector-regression/signextension-2.c",
        "c/bitvector-regression/signextension2-1.c",
        "c/bitvector-regression/signextension2-2.c",
        "c/loops/count_up_down-1.c",
        "c/loops/count_up_down-2.c",
    }
)

# Pilot supports only 32-bit integer nondet types (AArch64 AAPCS64 w0–w7).
NONDET_TYPE_MAP: dict[str, str] = {
    "__VERIFIER_nondet_int":  "int",
    "__VERIFIER_nondet_uint": "unsigned int",
}

NONDET_REJECT_TYPES: dict[str, str] = {
    "__VERIFIER_nondet_long":    "long (LP64 64-bit; not in pilot scope)",
    "__VERIFIER_nondet_ulong":   "unsigned long (LP64 64-bit; not in pilot scope)",
    "__VERIFIER_nondet_char":    "char (sub-register; not in pilot scope)",
    "__VERIFIER_nondet_uchar":   "unsigned char (sub-register; not in pilot scope)",
    "__VERIFIER_nondet_short":   "short (sub-register; not in pilot scope)",
    "__VERIFIER_nondet_ushort":  "unsigned short (sub-register; not in pilot scope)",
    "__VERIFIER_nondet_float":   "float (FP; SCOPE.md §5)",
    "__VERIFIER_nondet_double":  "double (FP; SCOPE.md §5)",
    "__VERIFIER_nondet_pointer": "pointer (heap; SCOPE.md §5)",
}

_REJECT_PATTERNS = (
    (re.compile(r"\b__VERIFIER_assume\s*\("), "uses __VERIFIER_assume"),
    (re.compile(r"\b(malloc|calloc|realloc|free)\s*\("), "uses heap allocation"),
    (re.compile(r"\bpthread_"),                "uses pthread"),
    (re.compile(r"#include\s*<stdio\.h>"),     "uses stdio"),
    (re.compile(r"\bfopen\s*\("),              "uses FILE I/O"),
    (re.compile(r"#include\s*<.*string\.h>"),  "uses string.h"),
)

# AArch64 bad-halt instruction (distinct PC from svc #0 normal halt).
_TRAP_DEF = """

void trap(void) {
    __asm__ volatile ("brk #0");
    __builtin_unreachable();
}
"""


@dataclass
class ExtractionPlan:
    nondet_args: list[tuple[str, str]]  # (c_type, arg_name)
    rewritten_c: str


# ---------------------------------------------------------------------------
# Internal helpers — ported from bench/riscv-btor2/corpus/_svcomp_extract.py
# with AArch64 adaptations noted inline.
# ---------------------------------------------------------------------------


def _parse_yml_unreach_call(yml_text: str) -> bool | None:
    """Return the unreach-call expected_verdict or None if absent."""
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
    return sorted(
        (m.start(), m.group(1))
        for m in re.finditer(r"\b(__VERIFIER_nondet_[A-Za-z_]+)\s*\(", src)
    )


def _strip_extern_decls(src: str) -> str:
    """Remove SV-COMP boilerplate declarations/definitions."""
    patterns = [
        r"^extern\s+void\s+abort\s*\(\s*void\s*\)\s*;\s*$",
        r"^extern\s+void\s+__assert_fail\s*\([^;]*\)\s*[^;]*;\s*$",
        r"^extern\s+\w[\w\s\*]*\s+__VERIFIER_nondet_\w+\s*\(\s*(void)?\s*\)\s*;\s*$",
        r"^\w[\w\s\*]*\s+__VERIFIER_nondet_\w+\s*\(\s*\)\s*;\s*$",
        r"^#include\s*<assert\.h>\s*$",
    ]
    for pat in patterns:
        src = re.sub(pat, "", src, flags=re.MULTILINE)
    src = _strip_function(src, "reach_error")
    src = _strip_function(src, "__VERIFIER_assert")
    return src


def _strip_function(src: str, name: str) -> str:
    """Remove a free-standing C function definition named ``name``."""
    pat = re.compile(
        r"(?P<head>\b\w[\w\s\*]*\s+" + re.escape(name) + r"\s*\([^)]*\)\s*)\{",
    )
    while True:
        m = pat.search(src)
        if m is None:
            return src
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
        src = src[: m.start()] + src[i:]


def _shim_header(
    *, original_path: str, svcomp_verdict: str, bench_verdict: str
) -> str:
    return (
        "// Generated by bench/aarch64-btor2/corpus/_svcomp_stream.py\n"
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


def _rewrite_main(src: str, nondets: list[tuple[str, str]]) -> str:
    """Rename ``int main(...)`` to ``int task_main(<args>)`` and append
    an AArch64 ``_start`` that routes nondet args through w0..wN registers.

    AArch64 AAPCS64: 32-bit integer args live in w0–w7 (lower 32 bits of
    x0–x7).  Normal halt is ``svc #0``; bad halt is ``brk #0`` (in trap).
    """
    sig = ", ".join(f"{c_type} {arg_name}" for c_type, arg_name in nondets) or "void"
    new_src, n = re.subn(
        r"\bint\s+main\s*\([^)]*\)",
        f"int task_main({sig})",
        src,
        count=1,
    )
    if n != 1:
        raise ValueError("could not locate `int main(...)` to rename")
    asm_decls = "\n".join(
        f'    register {c_type} {arg_name} __asm__("w{i}");'
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
    __asm__ volatile ("svc #0");
}}
"""
    return new_src + start + _TRAP_DEF


def _plan(src: str) -> ExtractionPlan:
    """Strip SV-COMP boilerplate, identify nondets, rewrite call sites."""
    src = _strip_extern_decls(src)
    calls = _find_nondet_calls(src)
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
        base = "v"
        i = len(nondet_args)
        name = f"{base}{i}"
        while name in seen_arg_names:
            i += 1
            name = f"{base}{i}"
        seen_arg_names.add(name)
        nondet_args.append((c_type, name))

    arg_iter = iter(nondet_args)

    def replace(_match: re.Match) -> str:
        try:
            _, arg_name = next(arg_iter)
        except StopIteration:  # pragma: no cover — logic error
            raise RuntimeError("nondet replacement ran out of args")
        return arg_name

    rewritten = re.sub(
        r"\b__VERIFIER_nondet_[A-Za-z_]+\s*\(\s*\)",
        replace,
        src,
    )
    return ExtractionPlan(nondet_args=nondet_args, rewritten_c=rewritten)


def _validate_entry_only(src: str, nondet_count: int) -> None:
    """For the pilot, every nondet call must appear before the first
    control-flow keyword in ``main``'s body."""
    if nondet_count == 0:
        return
    main_match = re.search(r"\bint\s+main\s*\([^)]*\)\s*\{", src)
    if not main_match:
        raise ValueError("no `int main(...)` body found")
    body_start = main_match.end()
    body = src[body_start:]
    cf = re.search(r"\b(if|while|for|do|switch|goto)\b", body)
    nd = re.search(r"\b__VERIFIER_nondet_", body)
    if cf is None or nd is None:
        return
    if nd.start() > cf.start():
        raise ValueError(
            "nondet appears AFTER first control-flow keyword in main — "
            "not entry-only; pilot rejects this shape"
        )


def _task_toml(
    *,
    task_id: str,
    bench_verdict: str,
    svcomp_pick: str,
    yml_data_model: str | None,
    nondet_args: list[tuple[str, str]],
    bound: int,
) -> str:
    nondet_summary = (
        "; ".join(f"{t} {n}" for t, n in nondet_args) if nondet_args else "none"
    )
    source_url = _SV_RAW_BASE + svcomp_pick
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

[svcomp_stream]
extractor_version = "{EXTRACTOR_VERSION}"
svcomp_pick       = "{svcomp_pick}"
sv_bench_commit   = "{_PINNED_COMMIT}"
svcomp_data_model = "{yml_data_model or 'unset'}"
nondet_args       = "{nondet_summary}"

[notes]
text = \"\"\"
aarch64-btor2 pilot — vendored from sv-benchmarks via streaming fetch.
The bench's expected verdict is derived mechanically from the SV-COMP
`.yml` (the `unreach-call.prp` property's `expected_verdict`: true →
unreachable, false → reachable). Pinned to -O0.

Source URL: {source_url}

The SV-COMP source is in `original.c`; the rewriter's output is
`task.c`. The rewriter (`bench/aarch64-btor2/corpus/_svcomp_stream.py`,
version {EXTRACTOR_VERSION}) translates `reach_error()`/`abort()`/
`__VERIFIER_assert` into the bench's `trap()` convention and (for
entry-only nondets) routes `__VERIFIER_nondet_*` returns through
AArch64 AAPCS64 argument registers w0..wN that are uninitialized at
`_start` (hence symbolic in the bench's BMC).
\"\"\"
"""


# ---------------------------------------------------------------------------
# URL fetch
# ---------------------------------------------------------------------------


def _raw_url(pick: str) -> str:
    """Return the raw GitHub URL for a sv-benchmarks pick path."""
    return _SV_RAW_BASE + pick


def _fetch(url: str) -> str:
    """Fetch ``url`` and return decoded text.  Caps at _MAX_FETCH_BYTES."""
    with urlopen(url, timeout=30) as resp:
        raw = resp.read(_MAX_FETCH_BYTES + 1)
    if len(raw) > _MAX_FETCH_BYTES:
        raise ValueError(
            f"remote file exceeds {_MAX_FETCH_BYTES} bytes — not in pilot scope"
        )
    return raw.decode("utf-8", errors="strict")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def bench_verdict_is_reachable(v: str) -> bool:
    return v == "reachable"


def stream(
    *,
    pick: str,
    task_id: str,
    out_root: Path,
    bound: int,
) -> Path:
    """Fetch one SV-COMP task from GitHub and emit a corpus task directory.

    Returns the created task directory path.
    Raises ``ValueError`` if ``pick`` is not in WHITELIST.
    """
    if pick not in WHITELIST:
        raise ValueError(
            f"{pick!r} is not in the aarch64-btor2 svcomp_stream whitelist"
        )

    c_url = _raw_url(pick)
    yml_url = _raw_url(pick.rsplit(".", 1)[0] + ".yml")

    raw = _fetch(c_url)
    yml = _fetch(yml_url)

    reject = _check_rejects(raw)
    if reject is not None:
        raise ValueError(f"rejected: {reject}")

    unreach = _parse_yml_unreach_call(yml)
    if unreach is None:
        raise ValueError(
            "no unreach-call property in .yml — pilot does not support "
            "other property shapes yet"
        )
    bench_verdict = "unreachable" if unreach else "reachable"

    plan = _plan(raw)
    _validate_entry_only(plan.rewritten_c, len(plan.nondet_args))

    svcomp_verdict = str(not bench_verdict_is_reachable(bench_verdict)).lower()
    final = _shim_header(
        original_path=pick,
        svcomp_verdict=svcomp_verdict,
        bench_verdict=bench_verdict,
    ) + _rewrite_main(plan.rewritten_c, plan.nondet_args)

    task_dir = out_root / task_id
    task_dir.mkdir(parents=True, exist_ok=False)
    (task_dir / "original.c").write_text(raw, encoding="utf-8")
    (task_dir / "original.yml").write_text(yml, encoding="utf-8")
    (task_dir / "task.c").write_text(final, encoding="utf-8")
    (task_dir / "task.toml").write_text(
        _task_toml(
            task_id=task_id,
            bench_verdict=bench_verdict,
            svcomp_pick=pick,
            yml_data_model=_yml_data_model(yml),
            nondet_args=plan.nondet_args,
            bound=bound,
        ),
        encoding="utf-8",
    )
    return task_dir


def _try_compile(task_dir: Path) -> bool:
    """Attempt compilation via _compile_c.py.

    Returns True on success, False if aarch64-linux-gnu-gcc is absent.
    """
    if shutil.which("aarch64-linux-gnu-gcc") is None:
        return False
    subprocess.run(
        [sys.executable, str(_HERE / "_compile_c.py"), str(task_dir)],
        check=True,
    )
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pick",
        required=True,
        help="SV-COMP pick path, e.g. c/bitvector-regression/implicitunsignedconversion-1.c",
    )
    ap.add_argument(
        "--task-id",
        required=True,
        help="corpus task ID, e.g. 0250-svcomp-implicit-uns-conv-1",
    )
    ap.add_argument(
        "--out-root",
        type=Path,
        default=Path("bench/aarch64-btor2/corpus/svcomp_slice"),
        help="output root directory (default: bench/aarch64-btor2/corpus/svcomp_slice)",
    )
    ap.add_argument("--bound", type=int, default=60)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="skip compilation even if the cross-toolchain is present",
    )
    args = ap.parse_args(argv)

    try:
        task_dir = stream(
            pick=args.pick,
            task_id=args.task_id,
            out_root=args.out_root.resolve(),
            bound=args.bound,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        rel = task_dir.relative_to(Path.cwd().resolve())
    except ValueError:
        rel = task_dir
    print(f"wrote {rel}")

    if args.dry_run:
        print("skipped compilation (--dry-run)")
        return 0

    compiled = _try_compile(task_dir)
    if not compiled:
        print(
            "skipped compilation (aarch64-linux-gnu-gcc not found; "
            "spec.json not emitted)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
