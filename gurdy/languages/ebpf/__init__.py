"""The shared eBPF language + interpreter (languages/ebpf brief).

Registers the ``ebpf`` language with its deterministic source interpreter,
reused by every eBPF pair (currently ``ebpf-btor2``).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .interp import BpfProgram, program_from_words, run

__all__ = ["run", "BpfProgram", "program_from_words"]

register_language(Language("ebpf", source_interpreter=run))
