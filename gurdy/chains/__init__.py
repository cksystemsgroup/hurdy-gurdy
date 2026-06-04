"""Chains: compositions of hops/pairs into multi-hop translations.

A chain runs an instance through several edges of the language graph,
threading provenance and the transitive source map across hops. The
first chain is ``c_to_btor2`` (C -> RV64 ELF -> BTOR2), composing the
``gurdy.hops.c_riscv`` compile hop with the ``riscv-btor2`` pair. See
the repo-root ``DESIGN_c_to_btor2_chain.md`` and
``DESIGN_generalized_pairs.md`` (Appendix A: chains as pasted squares).
"""
