#!/usr/bin/env python3
"""Guard the appendix's frozen crosswalk (run by `make` after main.pdf).

The standalone appendix (appendix/appendix.tex + body.tex) refers to the
paper's theorems by HARDCODED numbers — it cannot \\Cref across documents.
Anything that shifts the shared theorem counter (a new numbered
definition, a numbered example) silently invalidates them. This script
parses main.aux and asserts every frozen reference still names the same
result; the build fails loudly if not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# label -> (frozen number, human name) as written in appendix/{appendix,body}.tex
FROZEN = {
    "def:faithful": ("3.5", "Faithfulness"),
    "def:support": ("3.6", "Support"),
    "thm:pasting": ("3.7", "Pasting"),
    "cor:localization": ("3.8", "Localization"),
    "prop:cache": ("3.9", "Determinism and caching"),
    "prop:weakestlink": ("4.2", "Weakest link"),
    "def:coverage": ("4.6", "Coverage"),
    "prop:ratchet": ("4.7", "Ratchet"),
    "sec:evaluation": ("6", "Evaluation"),
}


def main() -> int:
    aux = (HERE / "main.aux").read_text(encoding="latin-1")
    labels = dict(re.findall(r"\\newlabel\{([^}]*)\}\{\{([0-9.]+)\}", aux))
    bad = []
    for label, (num, name) in FROZEN.items():
        actual = labels.get(label)
        if actual != num:
            bad.append(f"  {label} ({name}): appendix says {num}, "
                       f"main.aux says {actual}")
    if bad:
        print("CROSSWALK BROKEN — the appendix's frozen numbers no longer "
              "match the paper:")
        print("\n".join(bad))
        print("Update appendix/appendix.tex + appendix/body.tex (and this "
              "script's FROZEN table).")
        return 1
    print(f"crosswalk OK ({len(FROZEN)} frozen references match main.aux)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
