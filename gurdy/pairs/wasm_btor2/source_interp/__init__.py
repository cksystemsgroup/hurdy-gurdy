"""WebAssembly concrete executor.

Stack machine + locals + globals + linear memory + function tables.
Implements ``run(module, scope, inputs) -> trace`` and a shadow mode
that records per-instruction state cell reads/writes for the
alignment oracle. See ``V2_BOOTSTRAP.md`` §3.1.

Implementation begins at P2.
"""
