"""Shared, standalone language interpreters (ARCHITECTURE.md §§5-6).

Each ``gurdy.languages.<lang>`` module owns its language's deterministic
interpreter and registers the ``Language`` with the framework. Interpreters
are built as standalone deliverables, before pairs (FRAMEWORK.md §1). The
language's brief/contract lives at the top-level ``languages/<lang>/``.
"""
