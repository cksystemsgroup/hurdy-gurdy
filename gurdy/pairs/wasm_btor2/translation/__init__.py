"""WebAssembly → BTOR2 translator.

Deterministic, schema-pinned. Layered artifact (header / machine /
library / dispatch / init / constraint / bad / binding). See
``V2_BOOTSTRAP.md`` §3.3.

Implementation begins at P4.
"""
