"""The pinned toolchain for the `c-riscv` compile hop.

Everything in this module fixes the emitted bytes. The flag tuples are
the hop's *canonical translation rules* (the opaque-hop analogue of a
pair's SCHEMA): changing any of them is a versioned change to
``CONTRACT.md``. Reproducibility is anchored on the image *digest*, not
a moving tag — see ``CONTRACT.md`` §"Reproducibility".
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Canonical translation rules (changing these changes ELF bytes) ---

# Shared, opt-independent flags. Mirror the corpus assembly/C build so
# the entry PC and ISA match across paths (``-Wl,-Ttext`` / ISA), with
# the reproducibility flag (``-ffile-prefix-map``) added by
# ``compile._flags_for`` because it references the pin's workdir.
BASE_CFLAGS: tuple[str, ...] = (
    "-march=rv64imc",
    "-mabi=lp64",
    "-nostdlib",
    "-nostartfiles",
    "-ffreestanding",
    "-g",
)
LINK_FLAGS: tuple[str, ...] = (
    "-Wl,-Ttext=0x10000",
    "-Wl,--no-relax",
)

# Pin any embedded timestamp to a fixed value (belt-and-suspenders; the
# RV64 ELF build does not normally embed build time, but this guarantees
# it cannot).
SOURCE_DATE_EPOCH = "0"

VALID_OPT_LEVELS = frozenset({"0", "1", "2", "3", "s", "g"})

# --- The pin ---

_DEFAULT_IMAGE = "christophkirsch/hurdy-gurdy-bench"
# Resolved digest of :latest at the time this hop was built. Pinning by
# digest (not :latest) is what makes the toolchain reproducible.
_DEFAULT_DIGEST = (
    "sha256:8bcc25f7b9cde6482167af9e8e33ffd81491b2a16ff6c2ca7375f83a82d1c348"
)
_DEFAULT_COMPILER = "riscv64-unknown-elf-gcc"
_DEFAULT_COMPILER_VERSION = "14.2.0"


@dataclass(frozen=True)
class ToolchainPin:
    """A reproducible compiler, identified by container image digest.

    ``ref`` is what is passed to ``docker run`` — always ``image@digest``
    so the same bytes come out on any host that can resolve the digest.
    """

    image: str
    digest: str
    compiler: str = _DEFAULT_COMPILER
    compiler_version: str = _DEFAULT_COMPILER_VERSION
    container_workdir: str = "/src"

    @property
    def ref(self) -> str:
        return f"{self.image}@{self.digest}"


def default_pin() -> ToolchainPin:
    """The pin this hop was built and tested against."""
    return ToolchainPin(image=_DEFAULT_IMAGE, digest=_DEFAULT_DIGEST)


__all__ = [
    "BASE_CFLAGS",
    "LINK_FLAGS",
    "SOURCE_DATE_EPOCH",
    "VALID_OPT_LEVELS",
    "ToolchainPin",
    "default_pin",
]
