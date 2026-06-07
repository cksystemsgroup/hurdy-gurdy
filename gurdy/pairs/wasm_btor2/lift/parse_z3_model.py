"""Parser for z3 model text strings.

z3's ``str(model)`` produces lines of the form::

    [name1 = val1,
     name2 = val2, ...]

Values can be:

- Plain decimal integers: ``42``, ``0``, ``4294967295``
- SMT-LIB hex literals:   ``#x0000002a``
- SMT-LIB binary literals: ``#b00101010``
- C-style hex literals:   ``0x2a``  (uncommon but handled defensively)

Negative decimal values from z3 are treated as unsigned by the caller;
this parser stores them as Python ints and lets the lifter apply the
appropriate bitmask.
"""

from __future__ import annotations

import re


_ASSIGNMENT_RE = re.compile(
    r'(?:^|[\[,\s])'          # token boundary
    r'([A-Za-z_][A-Za-z0-9_!]*)'  # variable name (z3 uses ! for step suffix)
    r'\s*=\s*'
    r'(#x[0-9a-fA-F]+'        # SMT-LIB hex
    r'|#b[01]+'               # SMT-LIB binary
    r'|0x[0-9a-fA-F]+'        # C-style hex
    r'|-?\d+)',                # signed decimal
)


def parse_z3_model(witness_text: str) -> dict[str, int]:
    """Return {variable_name: integer_value} for all assignments in the model text."""
    result: dict[str, int] = {}
    for m in _ASSIGNMENT_RE.finditer(witness_text):
        name = m.group(1)
        raw = m.group(2)
        if raw.startswith('#x'):
            val = int(raw[2:], 16)
        elif raw.startswith('#b'):
            val = int(raw[2:], 2)
        elif raw.startswith('0x'):
            val = int(raw[2:], 16)
        else:
            val = int(raw)
        result[name] = val
    return result


__all__ = ["parse_z3_model"]
