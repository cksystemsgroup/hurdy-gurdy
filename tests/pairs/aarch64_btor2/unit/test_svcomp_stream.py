"""Tests for bench/aarch64-btor2/corpus/_svcomp_stream.py — P12."""

from __future__ import annotations

import pathlib
import sys
from io import StringIO
from unittest.mock import patch

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[4]
_CORPUS_DIR = _REPO / "bench" / "aarch64-btor2" / "corpus"
sys.path.insert(0, str(_CORPUS_DIR))

import _svcomp_stream as _ss  # noqa: E402
from _svcomp_stream import (  # noqa: E402
    WHITELIST,
    _PINNED_COMMIT,
    _SV_RAW_BASE,
    _parse_yml_unreach_call,
    _check_rejects,
    _strip_extern_decls,
    _plan,
    _rewrite_main,
    _shim_header,
    _task_toml,
    _raw_url,
    bench_verdict_is_reachable,
    stream,
    main,
)

# ---------------------------------------------------------------------------
# Minimal SV-COMP fixtures (no network needed)
# ---------------------------------------------------------------------------

# implicitunsignedconversion-1.c — zero nondets, verdict reachable
_C_NO_NONDET = """\
extern void abort(void);
extern void __assert_fail(const char *, const char *, unsigned int, const char *) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));
void reach_error() { __assert_fail("0", "implicitunsignedconversion-1.c", 3, "reach_error"); }

int main() {
  unsigned int plus_one = 1;
  int minus_one = -1;

  if(plus_one < minus_one) {
    goto ERROR;
  }

  return (0);
  ERROR: {reach_error();abort();}
  return (-1);
}
"""

_YML_REACHABLE = """\
format_version: '2.0'
input_files: 'implicitunsignedconversion-1.c'
properties:
  - property_file: ../properties/unreach-call.prp
    expected_verdict: false
options:
  language: C
  data_model: ILP32
"""

# count_up_down-1.c — one unsigned int nondet, verdict unreachable
_C_ONE_UINT_NONDET = """\
extern void abort(void);
extern void __assert_fail(const char *, const char *, unsigned int, const char *) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));
void reach_error() { __assert_fail("0", "count_up_down-1.c", 3, "reach_error"); }

void __VERIFIER_assert(int cond) {
  if (!(cond)) {
    ERROR: {reach_error();abort();}
  }
  return;
}
unsigned int __VERIFIER_nondet_uint();

int main()
{
  unsigned int n = __VERIFIER_nondet_uint();
  unsigned int x=n, y=0;
  while(x>0)
  {
    x--;
    y++;
  }
  __VERIFIER_assert(y==n);
}
"""

_YML_UNREACHABLE = """\
format_version: '2.0'
input_files: 'count_up_down-1.c'
properties:
  - property_file: ../properties/unreach-call.prp
    expected_verdict: true
options:
  language: C
  data_model: ILP32
"""


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------


def test_whitelist_has_ten_entries():
    assert len(WHITELIST) == 10


def test_whitelist_contains_bitvector_and_loops():
    bv = [p for p in WHITELIST if p.startswith("c/bitvector-regression/")]
    loops = [p for p in WHITELIST if p.startswith("c/loops/")]
    assert len(bv) == 8
    assert len(loops) == 2


def test_raw_url_format():
    pick = "c/bitvector-regression/implicitunsignedconversion-1.c"
    url = _raw_url(pick)
    assert url.startswith("https://raw.githubusercontent.com/sosy-lab/sv-benchmarks/")
    assert _PINNED_COMMIT in url
    assert url.endswith(pick)


# ---------------------------------------------------------------------------
# YML parsing
# ---------------------------------------------------------------------------


def test_parse_yml_unreach_call_false_gives_reachable():
    result = _parse_yml_unreach_call(_YML_REACHABLE)
    assert result is False  # expected_verdict: false → property fails → reachable


def test_parse_yml_unreach_call_true_gives_unreachable():
    result = _parse_yml_unreach_call(_YML_UNREACHABLE)
    assert result is True  # expected_verdict: true → property holds → unreachable


def test_parse_yml_unreach_call_none_when_absent():
    yml = "format_version: '2.0'\nproperties:\n  - property_file: ../properties/termination.prp\n    expected_verdict: true\n"
    assert _parse_yml_unreach_call(yml) is None


# ---------------------------------------------------------------------------
# Reject patterns
# ---------------------------------------------------------------------------


def test_check_rejects_verifier_assume():
    src = "int main() { int x = __VERIFIER_nondet_int(); __VERIFIER_assume(x > 0); }"
    assert _check_rejects(src) == "uses __VERIFIER_assume"


def test_check_rejects_malloc():
    src = "#include <stdlib.h>\nint main() { void *p = malloc(4); }"
    assert _check_rejects(src) == "uses heap allocation"


def test_check_rejects_clean_source():
    src = "int main() { int x = 1; if (x) reach_error(); }"
    assert _check_rejects(src) is None


# ---------------------------------------------------------------------------
# _rewrite_main — AArch64-specific: w0..wN, svc #0, brk #0
# ---------------------------------------------------------------------------


def test_rewrite_main_no_nondets_uses_svc0():
    src = "int main(void) { return 0; }"
    result = _rewrite_main(src, [])
    assert '__asm__ volatile ("svc #0")' in result
    assert "task_main();" in result
    assert "w0" not in result  # no register declarations


def test_rewrite_main_no_nondets_trap_uses_brk0():
    src = "int main(void) { return 0; }"
    result = _rewrite_main(src, [])
    assert '__asm__ volatile ("brk #0")' in result


def test_rewrite_main_one_int_nondet_uses_w0():
    src = "int main(void) { return 0; }"
    result = _rewrite_main(src, [("int", "v0")])
    assert 'register int v0 __asm__("w0")' in result
    assert "task_main(v0);" in result
    assert '__asm__ volatile ("svc #0")' in result


def test_rewrite_main_one_uint_nondet_uses_w0():
    src = "int main(void) { return 0; }"
    result = _rewrite_main(src, [("unsigned int", "v0")])
    assert 'register unsigned int v0 __asm__("w0")' in result


def test_rewrite_main_two_nondets_uses_w0_w1():
    src = "int main(void) { return 0; }"
    result = _rewrite_main(src, [("int", "v0"), ("unsigned int", "v1")])
    assert 'register int v0 __asm__("w0")' in result
    assert 'register unsigned int v1 __asm__("w1")' in result
    assert "task_main(v0, v1);" in result


def test_rewrite_main_renames_main_to_task_main():
    src = "int main(void) { return 0; }"
    result = _rewrite_main(src, [])
    assert "int task_main(void)" in result
    assert "int main(" not in result


# ---------------------------------------------------------------------------
# _task_toml
# ---------------------------------------------------------------------------


def test_task_toml_has_svcomp_stream_section():
    toml_str = _task_toml(
        task_id="0250-svcomp-test",
        bench_verdict="reachable",
        svcomp_pick="c/bitvector-regression/implicitunsignedconversion-1.c",
        yml_data_model="ILP32",
        nondet_args=[],
        bound=60,
    )
    assert "[svcomp_stream]" in toml_str
    assert "svcomp_stream" in toml_str
    assert "svcomp_extract" not in toml_str  # must not use the riscv section name


def test_task_toml_pinned_commit():
    toml_str = _task_toml(
        task_id="0250-svcomp-test",
        bench_verdict="reachable",
        svcomp_pick="c/bitvector-regression/implicitunsignedconversion-1.c",
        yml_data_model="ILP32",
        nondet_args=[],
        bound=60,
    )
    assert _PINNED_COMMIT in toml_str


def test_task_toml_nondet_summary():
    toml_str = _task_toml(
        task_id="0258-svcomp-count",
        bench_verdict="unreachable",
        svcomp_pick="c/loops/count_up_down-1.c",
        yml_data_model="ILP32",
        nondet_args=[("unsigned int", "v0")],
        bound=60,
    )
    assert 'nondet_args       = "unsigned int v0"' in toml_str


def test_task_toml_aarch64_notes():
    toml_str = _task_toml(
        task_id="0250-svcomp-test",
        bench_verdict="reachable",
        svcomp_pick="c/bitvector-regression/implicitunsignedconversion-1.c",
        yml_data_model="ILP32",
        nondet_args=[],
        bound=60,
    )
    assert "w0..wN" in toml_str  # AArch64 register note
    assert "aarch64-btor2" in toml_str


# ---------------------------------------------------------------------------
# stream() — offline via mocked _fetch
# ---------------------------------------------------------------------------


def test_stream_rejects_unknown_pick(tmp_path):
    with pytest.raises(ValueError, match="not in the aarch64-btor2 svcomp_stream whitelist"):
        stream(
            pick="c/nonexistent/task.c",
            task_id="9999-test",
            out_root=tmp_path,
            bound=60,
        )


def test_stream_offline_no_nondets(tmp_path):
    pick = "c/bitvector-regression/implicitunsignedconversion-1.c"

    def fake_fetch(url: str) -> str:
        return _YML_REACHABLE if url.endswith(".yml") else _C_NO_NONDET

    with patch.object(_ss, "_fetch", side_effect=fake_fetch):
        task_dir = stream(pick=pick, task_id="0250-test", out_root=tmp_path, bound=60)

    assert (task_dir / "original.c").read_text() == _C_NO_NONDET
    assert (task_dir / "original.yml").read_text() == _YML_REACHABLE
    task_c = (task_dir / "task.c").read_text()
    assert '__asm__ volatile ("svc #0")' in task_c
    assert '__asm__ volatile ("brk #0")' in task_c
    assert "task_main(" in task_c
    task_toml = (task_dir / "task.toml").read_text()
    assert 'verdict = "reachable"' in task_toml
    assert "[svcomp_stream]" in task_toml


def test_stream_offline_one_uint_nondet(tmp_path):
    pick = "c/loops/count_up_down-1.c"

    def fake_fetch(url: str) -> str:
        return _YML_UNREACHABLE if url.endswith(".yml") else _C_ONE_UINT_NONDET

    with patch.object(_ss, "_fetch", side_effect=fake_fetch):
        task_dir = stream(pick=pick, task_id="0258-test", out_root=tmp_path, bound=60)

    task_c = (task_dir / "task.c").read_text()
    assert 'register unsigned int v0 __asm__("w0")' in task_c
    assert "task_main(v0);" in task_c
    task_toml = (task_dir / "task.toml").read_text()
    assert 'verdict = "unreachable"' in task_toml
    assert 'nondet_args       = "unsigned int v0"' in task_toml


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------


def test_main_unknown_pick_exits_1():
    rc = main(["--pick", "c/unknown/task.c", "--task-id", "9999-unknown"])
    assert rc == 1


def test_main_dry_run_mocked(tmp_path):
    pick = "c/bitvector-regression/implicitunsignedconversion-1.c"

    def fake_fetch(url: str) -> str:
        return _YML_REACHABLE if url.endswith(".yml") else _C_NO_NONDET

    with patch.object(_ss, "_fetch", side_effect=fake_fetch):
        rc = main(
            [
                "--pick", pick,
                "--task-id", "0250-dry-run-test",
                "--out-root", str(tmp_path),
                "--dry-run",
            ]
        )

    assert rc == 0
    task_dir = tmp_path / "0250-dry-run-test"
    assert (task_dir / "task.c").exists()
    assert (task_dir / "task.toml").exists()
    assert not (task_dir / "spec.json").exists()  # no compiler → no spec
