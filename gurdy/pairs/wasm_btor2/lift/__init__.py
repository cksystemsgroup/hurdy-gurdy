"""Witness lifter: solver witness → source-level facts.

Renders a counterexample as a sequence of WASM-level events
(input bindings, instruction reached, trap location). Implementation
begins after dispatch lands at P6.
"""
