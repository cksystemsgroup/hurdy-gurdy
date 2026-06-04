"""Compile-only hops: deterministic edges in the language graph that are
*not* solver-terminating `Pair`s.

A `Pair` (under `gurdy.pairs`) is the special case of a hop whose output
is a reasoning language with solvers and a lifter. A plain *hop* is any
other certified translation between two formal languages — for example
`c-riscv`, which compiles C to RV64 ELF and hands those bytes to the
`riscv-btor2` pair. See the repo-root `DESIGN_generalized_pairs.md` and
`DESIGN_c_to_btor2_chain.md`.
"""
