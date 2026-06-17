"""The C source language (languages/c brief).

C is the platform's highest-altitude *source*. Deliberately **no interpreter**
([`pairs/c-riscv`] establishes faithfulness on the lowered RISC-V program, not
by mirroring C execution) — so the language is registered with no source
interpreter; the `c-riscv` translator is a pinned compiler and an external C
verifier (cbmc, in-container) is the C-level oracle.
"""

from __future__ import annotations

from ...core.registry import Language, register_language

register_language(Language("c"))   # opaque source; no interpreter by design
