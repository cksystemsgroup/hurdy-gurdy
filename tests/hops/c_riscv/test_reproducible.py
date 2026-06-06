"""Reproducibility + preservation tests for the `c-riscv` compile hop.

Docker-guarded: the pinned bench image isn't guaranteed in CI, so these
skip when it's absent (mirroring the oracle_cross smoke test's pattern).
They run one tiny task (0100) and one container at a time — no parallelism.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gurdy.hops.c_riscv import compile_c, default_pin, toolchain_available

REPO = Path(__file__).resolve().parents[3]
TASK0100 = (
    REPO / "bench" / "riscv-btor2" / "corpus" / "0100-c-add-trap-correct" / "task.c"
)

# Independently-derived baseline: the canonical ELF for 0100 under the
# pinned image + canonical flags + source_name="task.c", confirmed by a
# manual `docker run` when this hop was built. Ties the Python path to
# that baseline so a regression in either is caught.
EXPECTED_0100_SHA = (
    "953bcd83d04ce7729f3cb081c60d1691fc9cefe397577e4e9284f12c02215dd8"
)

pytestmark = pytest.mark.skipif(
    not toolchain_available(),
    reason="pinned bench Docker image not available (c-riscv hop needs it)",
)


def _src() -> bytes:
    return TASK0100.read_bytes()


def test_compile_is_deterministic():
    a = compile_c(_src(), source_name="task.c")
    b = compile_c(_src(), source_name="task.c")
    assert a.elf_bytes == b.elf_bytes
    assert a.elf_sha256 == b.elf_sha256


def test_matches_independent_docker_baseline():
    r = compile_c(_src(), source_name="task.c")
    assert r.elf_sha256 == EXPECTED_0100_SHA


def test_no_host_path_leaks_into_elf():
    # The legacy corpus build embedded absolute host paths in DWARF; the
    # reproducible hop must not.
    r = compile_c(_src(), source_name="task.c")
    assert b"/Users/" not in r.elf_bytes
    assert str(REPO).encode() not in r.elf_bytes
    assert b"/private/var" not in r.elf_bytes


def test_provenance_records_pin_and_hashes():
    r = compile_c(_src(), source_name="task.c")
    p = r.provenance
    assert p.digest == default_pin().digest
    assert p.compiler_version == "14.2.0"
    assert p.source_name == "task.c"
    assert p.elf_sha256 == EXPECTED_0100_SHA
    assert f"-ffile-prefix-map={default_pin().container_workdir}=." in p.flags
    j = p.to_jsonable()
    assert j["elf_sha256"] == EXPECTED_0100_SHA
    assert j["source_sha256"] == p.source_sha256


def test_opt_level_changes_bytes():
    # A recorded parameter that changes the translation must change the
    # bytes (and stay deterministic).
    o0 = compile_c(_src(), source_name="task.c", opt_level="0")
    o2a = compile_c(_src(), source_name="task.c", opt_level="2")
    o2b = compile_c(_src(), source_name="task.c", opt_level="2")
    assert o2a.elf_bytes == o2b.elf_bytes
    assert o0.elf_sha256 != o2a.elf_sha256


def test_output_loads_as_riscv_for_hop2():
    # Hop 2 (riscv-btor2) consumes ELF *bytes* directly and decodes DWARF;
    # prove the handoff works end-to-end at the byte level.
    from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary

    r = compile_c(_src(), source_name="task.c")
    src = load_riscv_binary(r.elf_bytes)
    assert src.is_riscv


def test_bad_opt_level_rejected():
    with pytest.raises(ValueError):
        compile_c(_src(), opt_level="9")


def test_bad_source_name_rejected():
    with pytest.raises(ValueError):
        compile_c(_src(), source_name="evil; rm -rf /.c")
