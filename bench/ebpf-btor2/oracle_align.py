"""Bench-level alignment oracle entry point — delegates to the pair module."""

from gurdy.pairs.ebpf_btor2.oracle_align import (  # noqa: F401
    AlignmentFailure,
    ORACLE_VERSION,
    PAIR_ID,
    align,
)
