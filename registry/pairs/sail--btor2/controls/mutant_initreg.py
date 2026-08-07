import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.sail_btor2.translate import translate     # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    program = json.load(fh)
program.setdefault("init_regs", {})["5"] = 1
sys.stdout.write(translate(program).decode("utf-8"))
