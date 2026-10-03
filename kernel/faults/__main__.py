"""The fault-injection driver: see the package docstring."""

from __future__ import annotations

import os
import sys

from kernel import registry
from kernel.faults import admission, checkers, harness, mutate, play


def main(argv: list[str]) -> int:
    def option(flag: str, default):
        return type(default)(argv[argv.index(flag) + 1]) \
            if flag in argv else default
    flags = next((i for i, a in enumerate(argv) if a.startswith("--")),
                 len(argv))
    words = argv[1:flags]
    reg_root = option("--registry", "registry")
    harness.VERBOSE = True
    if argv[:1] == ["report"]:
        paths = words or (admission._result_files() + play.result_files()
                          + checkers.result_files())
        sys.stdout.write("\n".join(
            table for table in (admission.report(paths), play.report(paths),
                                checkers.report(paths)) if table))
        return 0
    reg = registry.load(reg_root)
    every = harness.targets(reg)
    if argv[:1] == ["targets"]:
        for t in every:
            with open(os.path.join(t["manifest"]["_dir"], t["file"]),
                      encoding="utf-8") as fh:
                count = len(mutate.sites(fh.read()))
            sys.stdout.write(f"{t['role']:9} {t['entry']} {t['file']} "
                             f"({count} sites)\n")
        return 0
    if argv[:1] == ["probe"]:
        seed = option("--seed", 1)
        out = option("--out", os.path.join(harness.RESULTS,
                                           "probe-languages.jsonl"))
        chosen = [t for t in every if t["file"].endswith("check.py")
                  and (not words or (t["entry"], t["file"]) == tuple(words))]
        if not chosen and len(words) == 2:
            chosen = [t for t in [harness.target_at(reg_root, *words)] if t]
        if not chosen:
            sys.stderr.write(f"no such checker: {' '.join(words)}\n")
            return 1
        for t in chosen:
            checkers.probe_target(
                reg_root, reg, t, seed, out,
                option("--gate", os.path.join(harness.RESULTS,
                                              "gate-languages.jsonl")),
                option("--runs", "runs"))
        return 0
    if argv[:1] in (["gate"], ["play"]) and words:
        n, seed = option("--n", 100), option("--seed", 1)
        if argv[0] == "play":             # judges are not played: a
            every = [t for t in every     # judge is what a play trusts
                     if t["role"] == "transport"]
        if words[0] == "all":
            chosen = every
        elif words[0] in harness.SUBS:
            chosen = [t for t in every if t["sub"] == words[0]]
        else:
            chosen = [t for t in every if t["entry"] == words[0]
                      and [t["file"]] == words[1:2]]
            if not chosen and len(words) == 2:
                chosen = [t for t in [harness.target_at(reg_root, *words)]
                          if t]
        if not chosen:
            sys.stderr.write(f"no such target: {' '.join(words)}\n")
            return 1
        failed = 0
        for t in chosen:
            out = option("--out", os.path.join(
                harness.RESULTS, f"{argv[0]}-{t['sub']}.jsonl"))
            try:
                if argv[0] == "gate":
                    admission.gate_target(reg_root, reg, t, n, seed, out,
                                          option("--like", ""))
                else:
                    play.play_target(reg_root, reg, t, n, seed, out,
                                     option("--runs", "runs"))
            except SystemExit as exc:     # a control failed: say so in
                failed += 1               # the results and go on
                harness.append(out, {"event": "aborted", "entry": t["entry"],
                                     "file": t["file"], "role": t["role"],
                                     "seed": seed, "why": str(exc)[:400]})
                sys.stderr.write(f"{exc}\n")
        return 1 if failed else 0
    sys.stderr.write(__import__("kernel.faults").faults.__doc__ or "")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
