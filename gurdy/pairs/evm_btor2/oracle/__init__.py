"""Alignment oracle for the evm-btor2 pair (P5).

``AlignmentOracle.check`` translates an ``EvmBtor2Spec`` to BTOR2,
feeds it to the concrete reasoning interpreter up to the spec's BMC
bound, and returns an ``AlignmentResult`` (bad_fired, witness_step,
btor2_model).
"""

from gurdy.pairs.evm_btor2.oracle.alignment import AlignmentOracle, AlignmentResult

__all__ = ["AlignmentOracle", "AlignmentResult"]
