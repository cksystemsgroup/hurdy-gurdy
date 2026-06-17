"""Coverage-slice loader/runner for the RISC-V compliance suites
(languages/riscv brief, BENCHMARKS.md §4): **riscv-tests** and
**riscv-arch-test**.

Both are bare-metal ELF programs (the pinned submodules are built with the
toolchain) that signal their result through one of two golden-state
conventions, which this module grades the shared interpreter against:

- **HTIF ``tohost``** (riscv-tests): the test writes a result word to the
  ``tohost`` symbol — ``1`` means pass, an odd ``(n<<1)|1`` means test ``n``
  failed. The interpreter halts on that write (``run(..., {"tohost": addr})``).
- **Signature** (riscv-arch-test): the test fills the memory region
  ``[begin_signature, end_signature)`` and a golden ``.signature`` reference
  (32-bit words, one per line) is compared against it.

The loader is gated on a suite directory being present (``$RISCV_TESTS_DIR``
or a path argument); the grading logic (``tohost_status``, ``parse_signature``,
``extract_signature``) is pure and unit-tested.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .elf import load_elf
from .interp import RiscvImage, run


@dataclass(frozen=True)
class TestResult:
    name: str
    status: str          # "pass" | "fail" | "incomplete" | "error"
    detail: str = ""
    isa: str = ""        # e.g. rv64ui / rv64um / rv64uc (parsed from the name)


@dataclass
class SuiteReport:
    results: list[TestResult] = field(default_factory=list)

    def _count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return self._count("pass")

    @property
    def ok(self) -> bool:
        return self.total > 0 and all(r.status == "pass" for r in self.results)

    def by_isa(self) -> dict[str, tuple[int, int]]:
        """isa -> (passed, total)."""
        out: dict[str, list[int]] = {}
        for r in self.results:
            slot = out.setdefault(r.isa or "?", [0, 0])
            slot[1] += 1
            if r.status == "pass":
                slot[0] += 1
        return {k: (v[0], v[1]) for k, v in out.items()}

    def summary(self) -> str:
        head = (f"{self.passed}/{self.total} pass  "
                f"(fail={self._count('fail')} incomplete={self._count('incomplete')} "
                f"error={self._count('error')})")
        by = "  ".join(f"{k}:{p}/{t}" for k, (p, t) in sorted(self.by_isa().items()))
        return head + ("\n" + by if by else "")


def tohost_status(value: int) -> tuple[str, str]:
    """Grade an HTIF ``tohost`` word: (status, detail)."""
    if value == 0:
        return "incomplete", "tohost never written (ran out of steps?)"
    if value == 1:
        return "pass", ""
    if value & 1:
        return "fail", f"failed test #{value >> 1}"
    return "error", f"unexpected tohost=0x{value:x}"


def parse_signature(text: str) -> list[int]:
    """Parse a golden ``.signature`` reference: one 32-bit hex word per line."""
    return [int(tok, 16) for tok in text.split() if tok.strip()]


def extract_signature(image: RiscvImage) -> list[int]:
    """Read the [begin_signature, end_signature) region as 32-bit words."""
    lo = image.symbols["begin_signature"]
    hi = image.symbols["end_signature"]
    return [image.load(lo + 4 * i, 4) for i in range((hi - lo) // 4)]


def _isa_of(name: str) -> str:
    # riscv-tests binaries are named like rv64ui-p-add, rv64um-p-mul, ...
    head = name.split("-", 1)[0]
    return head if head.startswith("rv") else ""


def _run_image(image: RiscvImage, max_steps: int) -> None:
    binding = {"tohost": image.symbols["tohost"]} if "tohost" in image.symbols else {}
    run(image, binding, max_steps=max_steps)


def run_elf_test(elf_bytes: bytes, name: str = "?", max_steps: int = 1_000_000) -> TestResult:
    """Run one riscv-tests-style ELF and grade it via the ``tohost`` word."""
    isa = _isa_of(name)
    try:
        image = load_elf(elf_bytes)
        if "tohost" not in image.symbols:
            return TestResult(name, "error", "no tohost symbol", isa)
        _run_image(image, max_steps)
        status, detail = tohost_status(image.load(image.symbols["tohost"], 8))
        return TestResult(name, status, detail, isa)
    except Exception as e:  # a transl/decoding abort is a real (recorded) outcome
        return TestResult(name, "error", f"{type(e).__name__}: {e}", isa)


def run_signature_test(elf_bytes: bytes, golden: str, name: str = "?",
                       max_steps: int = 1_000_000) -> TestResult:
    """Run one riscv-arch-test-style ELF and compare its signature to golden."""
    isa = _isa_of(name)
    try:
        image = load_elf(elf_bytes)
        _run_image(image, max_steps)
        got, want = extract_signature(image), parse_signature(golden)
        if got == want:
            return TestResult(name, "pass", "", isa)
        for i, (g, w) in enumerate(zip(got, want)):
            if g != w:
                return TestResult(name, "fail", f"word {i}: 0x{g:08x} != 0x{w:08x}", isa)
        return TestResult(name, "fail", f"length {len(got)} != {len(want)}", isa)
    except Exception as e:
        return TestResult(name, "error", f"{type(e).__name__}: {e}", isa)


def discover(root: str | os.PathLike) -> list[Path]:
    """Find compliance-test ELF binaries under ``root`` (riscv-tests have no
    extension; riscv-arch-test use ``.elf``)."""
    out: list[Path] = []
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and p.suffix in ("", ".elf"):
            try:
                with open(p, "rb") as f:
                    if f.read(4) == b"\x7fELF":
                        out.append(p)
            except OSError:
                pass
    return out


def run_suite(root: str | os.PathLike, max_steps: int = 1_000_000) -> SuiteReport:
    """Discover and run every riscv-tests-style ELF under ``root``."""
    return SuiteReport([run_elf_test(p.read_bytes(), p.name, max_steps) for p in discover(root)])
