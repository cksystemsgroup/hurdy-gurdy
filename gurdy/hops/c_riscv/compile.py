"""Reproducible C -> RV64 ELF compilation: the ``c-riscv`` compile hop.

This is hop 1 of the ``C -> RV64 ELF -> BTOR2`` chain (see ``CONTRACT.md``
and the repo-root ``DESIGN_c_to_btor2_chain.md``). It is a *compile-only*
hop: deterministic, opaque-but-reproducible (trust tier ``reproducible``),
and it does no reasoning. Its sole job is to turn C source bytes into RV64
ELF bytes that are byte-identical for the same ``(source, pin, params)``
on any host, and to record the provenance needed to re-derive them.

It is deliberately **not** a ``Pair``: its output (an ELF) is not a
solver-terminating reasoning artifact. It composes with the
``riscv-btor2`` pair, whose loader consumes ELF *bytes* directly. (The
loader's ``from_elf`` is a sidecar-only stub with no in-process
``.debug_line`` decoder, so the path-normalized DWARF source map is
recovered separately by ``dwarf.extract_line_map``; see ``CONTRACT.md``.)

The reproducibility anchor is the pinned image, not the local toolchain:
on the build host, local gcc was 13.2.0 while the pinned image ships
14.2.0, and the legacy corpus build (``bench/.../corpus/_compile_c.py``)
additionally baked absolute host paths into DWARF. This hop fixes both
(see ``CONTRACT.md``).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass

from gurdy.hops.c_riscv.toolchain import (
    BASE_CFLAGS,
    LINK_FLAGS,
    SOURCE_DATE_EPOCH,
    VALID_OPT_LEVELS,
    ToolchainPin,
    default_pin,
)

# Logical source filename embedded in DWARF (and therefore in the bytes).
# Restricted to a safe charset because it is interpolated into the shell
# command run inside the container.
_SAFE_SOURCE_NAME = re.compile(r"\A[A-Za-z0-9_][A-Za-z0-9_.-]*\.c\Z")

_COMPILE_TIMEOUT_S = 300


class CompileError(RuntimeError):
    """The pinned compiler failed or produced no ELF."""


class ToolchainUnavailable(RuntimeError):
    """Docker or the pinned image is not available on this host."""


@dataclass(frozen=True)
class Provenance:
    """Everything needed to re-derive the ELF bytes from the source."""

    image: str
    digest: str
    compiler: str
    compiler_version: str
    flags: tuple[str, ...]
    opt_level: str
    source_name: str
    container_workdir: str
    source_date_epoch: str
    source_sha256: str
    elf_sha256: str

    def to_jsonable(self) -> dict:
        return {
            "image": self.image,
            "digest": self.digest,
            "compiler": self.compiler,
            "compiler_version": self.compiler_version,
            "flags": list(self.flags),
            "opt_level": self.opt_level,
            "source_name": self.source_name,
            "container_workdir": self.container_workdir,
            "source_date_epoch": self.source_date_epoch,
            "source_sha256": self.source_sha256,
            "elf_sha256": self.elf_sha256,
        }


@dataclass(frozen=True)
class CCompileResult:
    elf_bytes: bytes
    provenance: Provenance

    @property
    def elf_sha256(self) -> str:
        return self.provenance.elf_sha256


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _flags_for(opt_level: str, pin: ToolchainPin) -> tuple[str, ...]:
    """The full, ordered flag list. Order is part of the contract because
    it can affect emitted bytes."""
    return (
        f"-O{opt_level}",
        *BASE_CFLAGS,
        f"-ffile-prefix-map={pin.container_workdir}=.",
        *LINK_FLAGS,
    )


def toolchain_available(pin: ToolchainPin | None = None) -> bool:
    """True iff ``docker`` is on PATH and the pinned image is present.

    Used to gate the hop (and its tests) the way the pair gates optional
    solvers — installable and importable without the toolchain, usable
    only where it is present.
    """
    pin = pin or default_pin()
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", pin.ref],
            capture_output=True,
            timeout=30,
        )
        return proc.returncode == 0
    except Exception:
        return False


def compile_c(
    source: bytes | str,
    *,
    pin: ToolchainPin | None = None,
    opt_level: str = "0",
    source_name: str = "module.c",
) -> CCompileResult:
    """Compile C ``source`` to RV64 ELF bytes reproducibly.

    Same ``(source, pin, opt_level, source_name)`` -> byte-identical ELF
    on any host that can resolve the pin's image digest.

    ``source_name`` is the logical filename embedded in DWARF; it affects
    the bytes and the downstream source map, so it is recorded in
    provenance. Raises ``ToolchainUnavailable`` if the pinned image is
    not present, ``CompileError`` if the compiler fails.
    """
    pin = pin or default_pin()
    opt_level = str(opt_level)
    if opt_level not in VALID_OPT_LEVELS:
        raise ValueError(
            f"unknown opt_level {opt_level!r}; supported: {sorted(VALID_OPT_LEVELS)}"
        )
    if not _SAFE_SOURCE_NAME.match(source_name):
        raise ValueError(
            f"unsafe source_name {source_name!r}; must match {_SAFE_SOURCE_NAME.pattern}"
        )
    src = source.encode() if isinstance(source, str) else bytes(source)

    flags = _flags_for(opt_level, pin)
    elf = _run_compiler(src, source_name, flags, pin)

    provenance = Provenance(
        image=pin.image,
        digest=pin.digest,
        compiler=pin.compiler,
        compiler_version=pin.compiler_version,
        flags=flags,
        opt_level=opt_level,
        source_name=source_name,
        container_workdir=pin.container_workdir,
        source_date_epoch=SOURCE_DATE_EPOCH,
        source_sha256=_sha(src),
        elf_sha256=_sha(elf),
    )
    return CCompileResult(elf_bytes=elf, provenance=provenance)


def _run_compiler(
    src_bytes: bytes,
    source_name: str,
    flags: tuple[str, ...],
    pin: ToolchainPin,
) -> bytes:
    """Run the pinned compiler in a throwaway container.

    Source goes in on stdin (``cat > <name>``); the ELF comes back on
    stdout (``cat out.elf``) with compiler diagnostics redirected to
    stderr. No bind mount — this keeps the build independent of host
    file-sharing config, and compiling at the fixed ``container_workdir``
    (plus ``-ffile-prefix-map``) keeps the host path out of the DWARF.
    """
    if not toolchain_available(pin):
        raise ToolchainUnavailable(
            f"pinned toolchain {pin.ref} not available "
            "(need docker + the bench image)"
        )
    wd = pin.container_workdir
    flagstr = " ".join(flags)
    script = (
        f"set -e; mkdir -p {wd}; cd {wd}; cat > {source_name}; "
        f"{pin.compiler} {flagstr} -o out.elf {source_name} 1>&2; "
        f"cat out.elf"
    )
    cmd = [
        "docker",
        "run",
        "--rm",
        "-i",
        "-e",
        f"SOURCE_DATE_EPOCH={SOURCE_DATE_EPOCH}",
        pin.ref,
        "sh",
        "-c",
        script,
    ]
    try:
        proc = subprocess.run(
            cmd, input=src_bytes, capture_output=True, timeout=_COMPILE_TIMEOUT_S
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - env dependent
        raise CompileError(f"compile timed out after {_COMPILE_TIMEOUT_S}s") from exc

    stderr = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise CompileError(
            f"compile failed (exit {proc.returncode}):\n{stderr[-2000:]}"
        )
    elf = proc.stdout
    if not elf.startswith(b"\x7fELF"):
        raise CompileError(
            "compiler produced no ELF on stdout "
            f"({len(elf)} bytes); stderr:\n{stderr[-2000:]}"
        )
    return elf


__all__ = [
    "CCompileResult",
    "CompileError",
    "Provenance",
    "ToolchainUnavailable",
    "compile_c",
    "toolchain_available",
]
