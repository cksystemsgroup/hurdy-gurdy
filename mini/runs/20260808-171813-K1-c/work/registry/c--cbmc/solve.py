#!/usr/bin/env python3
"""c--cbmc: the cbmc bounded model checker as the decision procedure.
decides ["violation"]. Escalates --unwind until either cbmc reports
the user assertion FAILURE (witness, extracted from its JSON trace --
sound at any bound, cbmc treats an under-unwound loop as `assume`, not
`assert`, so a counterexample it finds is always real) or its own
--unwinding-assertions confirm the bound was enough (bound "inf").
"""
import json
import sys
import tempfile
import time

from cbmc_run import classify, run_cbmc, with_c_extension


def decide(program_path, wall_s):
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory() as d:
        c_path = with_c_extension(program_path, d)
        k = 8
        best_k = None
        while True:
            remaining = wall_s - (time.monotonic() - t0)
            if remaining < 2.0:
                if best_k is not None:
                    return {"kind": "all", "bound": best_k, "cert": None}
                return {"kind": "partial",
                        "progress": {"note": "wall budget exhausted",
                                    "bound_reached": 0}}
            data = run_cbmc(c_path, k, remaining)
            if data is None:
                if best_k is not None:
                    return {"kind": "all", "bound": best_k, "cert": None}
                return {"kind": "partial",
                        "progress": {"note": "cbmc failed or timed out",
                                    "unwind_tried": k}}
            witness_vals, unwind_insufficient, error = classify(data)
            if error is not None:
                return {"kind": "partial", "progress": {"note": error}}
            if witness_vals is not None:
                return {"kind": "witness", "payload": {"nondet": witness_vals}}
            if not unwind_insufficient:
                return {"kind": "all", "bound": "inf", "cert": {"unwind": k}}
            best_k = k
            if k >= 4096:
                return {"kind": "all", "bound": best_k, "cert": None}
            k *= 2


def main(argv):
    program, mode, observable, bound, wall_s = argv[:5]
    if observable != "violation":
        print(json.dumps({"kind": "partial",
                          "progress": {"note": f"cannot decide {observable!r}"}}))
        return 0
    print(json.dumps(decide(program, float(wall_s))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
