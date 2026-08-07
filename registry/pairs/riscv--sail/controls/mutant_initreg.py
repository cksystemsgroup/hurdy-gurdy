import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.riscv.interp import image_from_words  # noqa: E402
from gurdy.pairs.riscv_sail.translate import translate     # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    program = json.load(fh)
image = image_from_words([int(w) for w in program["words"]],
                         base=int(program.get("base", 0)),
                         entry=program.get("entry"))
out = json.loads(translate({"image": image}).decode("utf-8"))
out.setdefault("init_regs", {})["5"] = 1
sys.stdout.write(json.dumps(out, sort_keys=True))
