"""c--riscv wit channel (lam_wit): a riscv stimulus carried back as a c
stimulus. Frames align one-to-one (one fence per CFG node), and havoc
site h<n> reads riscv site <n>, so the carry-back is the renaming
"<n>" -> "h<n>" per frame — nothing else crosses, and the c
interpreter's replay is the only judge of the result.

Usage: lam_wit.py <target-input.json> <program.c> -> source input on stdout
"""

import json
import sys


def main():
    if len(sys.argv) != 3:
        print("usage: lam_wit.py <target-input.json> <program.c>",
              file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        stim = json.load(fh)
    steps = []
    for frame in stim.get("steps", []):
        out = {}
        for k, v in frame.items():
            if isinstance(k, str) and k.isdigit() and isinstance(v, int):
                out["h" + k] = v
        steps.append(out)
    print(json.dumps({"steps": steps}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
