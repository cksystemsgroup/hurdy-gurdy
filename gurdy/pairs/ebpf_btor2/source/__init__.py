"""eBPF source loader for the framework ``source_loader`` slot.

The ebpf-btor2 source is a flat sequence of 8-byte ``bpf_insn`` records
(the P1 subset; see ``source_interp.decode_program``). The framework
hands the translator whatever this loader returns, so the loader's job
is simply to resolve the caller's payload to raw bytecode bytes:

- ``bytes`` / ``bytearray``  → returned as-is.
- a path (``str`` / ``os.PathLike``) → the file's bytes.
- an object with a ``.path`` attribute (e.g. ``EbpfProgramRef``) → the
  bytes at that path.

Extracting a ``SEC(...)`` program section from a relocatable ``.bpf.o``
ELF is deferred (the P1 subset operates on flat bytecode); a path is
read verbatim.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def load_ebpf_source(payload: Any) -> bytes:
    if payload is None:
        raise ValueError(
            "ebpf-btor2 source_loader needs bytecode: pass the program bytes "
            "or a path as source_payload (the spec's program.path is not "
            "auto-inferred)."
        )
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    # EbpfProgramRef or any object carrying a filesystem path.
    path = getattr(payload, "path", payload)
    if isinstance(path, (str, os.PathLike)):
        return Path(path).read_bytes()
    raise TypeError(f"ebpf-btor2 source_loader cannot load payload of type {type(payload).__name__}")


__all__ = ["load_ebpf_source"]
