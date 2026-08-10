#!/usr/bin/env python3
"""Solver pair c -> result via cbmc: bounded model checking with a fixed,
input-derived (never wall-clock-derived) doubling schedule of unwind bounds,
so repeated runs on the same inputs are byte-identical. --no-standard-checks
strips CBMC's own UB assertions (overflow etc.) so only the user's assert()
decides `violation`. A witness is a counterexample's nondet_int() stream; a
completed unwinding-assertion pass at bound N is a full proof (bound=inf)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

NONDET_RE = re.compile(r'^return_value_nondet_int(\$\d+)?$')


def as_c_file(program):
    """cbmc identifies the source language from the file extension."""
    if program.endswith('.c'):
        return program
    fd, path = tempfile.mkstemp(suffix='.c')
    os.close(fd)
    shutil.copyfile(program, path)
    return path


def run_cbmc(program, unwind, wall):
    cfile = as_c_file(program)
    args = ['cbmc', cfile, '--no-standard-checks', '--unwind',
            str(unwind), '--unwinding-assertions', '--json-ui', '--trace']
    try:
        try:
            r = subprocess.run(args, capture_output=True, timeout=wall, text=True)
        except subprocess.TimeoutExpired:
            return None
    finally:
        if cfile != program:
            os.remove(cfile)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def analyze(data):
    violated, unwind_ok, nondet_vals = False, True, []
    for obj in data:
        if 'result' not in obj:
            continue
        for r in obj['result']:
            pid, status = r.get('property', ''), r.get('status')
            if pid.startswith('main.unwind.'):
                if status != 'SUCCESS':
                    unwind_ok = False
            elif pid.startswith('main.assertion.') and status == 'FAILURE':
                violated = True
                for step in r.get('trace', []):
                    if (step.get('stepType') == 'assignment'
                            and not step.get('hidden')
                            and NONDET_RE.match(step.get('lhs', ''))):
                        nondet_vals.append(int(step['value']['data']))
    return violated, nondet_vals, unwind_ok


def bound_schedule(wall_s):
    n_max = (2048 if wall_s >= 90 else 1024 if wall_s >= 30
             else 256 if wall_s >= 10 else 32)
    sched, n = [], 0
    while True:
        sched.append(n)
        if n >= n_max:
            return sched
        n = 1 if n == 0 else n * 2


def main():
    program = sys.argv[1]
    wall_s = float(sys.argv[5])
    schedule = bound_schedule(wall_s)
    last_ok = None
    tried = []
    for n in schedule:
        data = run_cbmc(program, n, wall_s)
        if data is None:
            break
        tried.append(n)
        violated, nondet_vals, unwind_ok = analyze(data)
        if violated:
            print(json.dumps({"kind": "witness",
                              "payload": {"nondet": nondet_vals}},
                             sort_keys=True))
            return
        last_ok = (n, unwind_ok)
        if unwind_ok:
            break
    if last_ok is None:
        print(json.dumps({"kind": "partial", "progress": {
            "note": "cbmc gave no usable verdict", "tried": tried}},
            sort_keys=True))
        return
    n, complete = last_ok
    print(json.dumps({"kind": "all", "bound": "inf" if complete else n,
                      "cert": {"unwind": n, "complete": complete}},
                     sort_keys=True))


if __name__ == '__main__':
    main()
