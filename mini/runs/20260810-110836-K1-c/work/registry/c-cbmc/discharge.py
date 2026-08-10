#!/usr/bin/env python3
"""Independent re-verification of a {"unwind": k, "complete": bool} claim:
re-run cbmc fresh at exactly that bound, on the source program, and check
the claim holds. complete=true additionally requires the unwinding
assertion to have held (no reachable state needs more than k iterations)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile


def as_c_file(program):
    if program.endswith('.c'):
        return program
    fd, path = tempfile.mkstemp(suffix='.c')
    os.close(fd)
    shutil.copyfile(program, path)
    return path


def run_cbmc(program, unwind, wall):
    cfile = as_c_file(program)
    args = ['cbmc', cfile, '--no-standard-checks', '--unwind', str(unwind),
            '--unwinding-assertions', '--json-ui', '--trace']
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
    violated, unwind_ok = False, True
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
    return violated, unwind_ok


def main():
    program, cert_path = sys.argv[1], sys.argv[2]
    try:
        with open(cert_path, encoding='utf-8') as fh:
            cert = json.load(fh)
        unwind = int(cert['unwind'])
        complete = bool(cert['complete'])
        if unwind < 0:
            raise ValueError('negative unwind')
    except Exception:
        print(json.dumps({"ok": False, "obligations": {}}))
        return
    data = run_cbmc(program, unwind, 60.0)
    if data is None:
        print(json.dumps({"ok": False, "obligations": {}}))
        return
    violated, unwind_ok = analyze(data)
    ok = (not violated) and (unwind_ok or not complete)
    obligations = {"unwind": unwind, "complete": complete,
                   "violated": violated, "unwind_ok": unwind_ok}
    print(json.dumps({"ok": ok, "obligations": obligations}, sort_keys=True))


if __name__ == '__main__':
    main()
