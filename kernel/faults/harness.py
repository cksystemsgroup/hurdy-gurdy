"""What both experiments stand on: the executables that can be
mutated, the probe every sealed run passes through, and the scratch
registry a mutant is staged in."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from kernel import registry, runner

_HERE = os.path.dirname(os.path.abspath(__file__))
COVER = os.path.join(_HERE, "cover.py")
RESULTS = os.path.join(_HERE, "results")
SUBS = ("domains", "languages", "pairs", "searches")
WALL_S = 60.0

#: A mutant may allocate without end where the intact file looped to a
#: bound; a run whose resident set passes this is killed like one that
#: passed its wall. The intact judges and transports stay far below it.
_RSS_CAP_MB = 2048
_POLL_S = 0.25

#: The carry-backs and maps a pair may ship besides its translator;
#: ``hint.py`` and a search's ``ledger.py`` are trust-inert and left out.
_PAIR_FILES = ("T.py", "lam_wit.py", "lam_cert.py", "lam_obs.py",
               "lam_in.py", "lam_bound.py")


# -- what can be mutated ------------------------------------------------------

def targets(reg: dict) -> list[dict]:
    """Every executable of every bound entry that carries trust or
    faces a judge: the judges of each language, the transports of each
    pair, the search of each search entry."""
    found = []
    for name, m in sorted(reg["languages"].items()):
        files = ["interp.py"] + [f"evidence/{s}/check.py"
                                 for s in registry.schemas(m)]
        found += [{"sub": "languages", "key": name, "manifest": m,
                   "file": f, "role": "judge"} for f in files]
    for pid, m in sorted(reg["pairs"].items()):
        found += [{"sub": "pairs", "key": pid, "manifest": m, "file": f,
                   "role": "transport"} for f in _PAIR_FILES
                  if os.path.isfile(os.path.join(m["_dir"], f))]
    for name, m in sorted(reg["searches"].items()):
        found.append({"sub": "searches", "key": name, "manifest": m,
                      "file": "solve.py", "role": "transport"})
    for t in found:
        t["entry"] = f"{t['sub']}/{os.path.basename(t['manifest']['_dir'])}"
    return [t for t in found if "admission" in t["manifest"]]


def target_at(reg_root: str, entry: str, file: str) -> dict | None:
    """The target for an admitted entry named by its directory, bound
    or not: a predecessor is measured like the revision that replaced
    it."""
    path = os.path.join(os.path.abspath(reg_root), entry)
    try:
        with open(os.path.join(path, "manifest.json"),
                  encoding="utf-8") as fh:
            manifest = json.load(fh)
    except OSError:
        return None
    sub = entry.split("/")[0]
    if "admission" not in manifest or not os.path.isfile(
            os.path.join(path, file)):
        return None
    manifest["_dir"] = path
    return {"sub": sub, "key": manifest.get("name") or manifest.get("id"),
            "manifest": manifest, "file": file, "entry": entry,
            "role": "judge" if sub == "languages" else "transport"}


# -- the probe: every sealed run the gate makes passes through here -----------

def _rss_mb(pid: int) -> float:
    res = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(pid)],
                         capture_output=True)
    try:
        return int(res.stdout.split()[0]) / 1024
    except (IndexError, ValueError):
        return 0.0


def _sealed(argv, stdin: bytes, wall_s: float, cwd) -> tuple:
    """``runner.run`` again — same seal, same scratch directory, same
    wall — with the resident set watched. Returns (result, peak MB
    seen, killed for memory)."""
    start, peak = time.monotonic(), 0.0
    with tempfile.TemporaryDirectory() as scratch:
        proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=cwd or scratch,
            env=runner.SEALED_ENV)
        data = stdin
        while True:
            left = wall_s - (time.monotonic() - start)
            try:
                out, err = proc.communicate(
                    data, timeout=max(0.0, min(_POLL_S, left)))
                return runner.RunResult(
                    out, err, proc.returncode,
                    time.monotonic() - start, False), peak, False
            except subprocess.TimeoutExpired:
                data = None            # sent once; a retry only reads
                peak = max(peak, _rss_mb(proc.pid))
                if peak > _RSS_CAP_MB or time.monotonic() - start >= wall_s:
                    proc.kill()
                    out, err = proc.communicate()
                    return runner.RunResult(
                        out or b"", err or b"", None,
                        time.monotonic() - start,
                        True), peak, peak > _RSS_CAP_MB


def _run_key(argv, stdin: bytes) -> str:
    """A sealed run named by what it reads: every argument that is a
    file by its bytes, every other argument by its text, and the
    standard input. Two runs of one key are one run — that is the
    determinism the gate measures on everything it admits."""
    h = hashlib.sha256()
    for i, arg in enumerate(argv):
        if i == 0 and arg == sys.executable:
            h.update(b"python")
        elif os.path.isfile(arg):
            with open(arg, "rb") as fh:
                h.update(b"file:" + hashlib.sha256(fh.read()).digest())
        else:
            h.update(b"text:" + arg.encode())
        h.update(b"\0")
    h.update(stdin)
    return h.hexdigest()


class Probe:
    """Stands in for ``runner.run`` while a target is exercised: caps the
    wall once the intact entry's longest run is known, kills a run
    that outgrows the memory cap, counts what the executable under
    test did, and, while the intact entry is gated, runs that
    executable under the line recorder.

    It also remembers. While the intact entry is exercised a run is
    executed once and its result kept under ``_run_key``, for this
    target and every later one in the process; while a mutant is
    exercised a run whose key is known is answered from memory and
    only the others execute — the mutated file's own runs, and
    whatever reads what they wrote. A mutant's own runs are executed twice per
    key before they are remembered, and only if the two agree, so the
    gate's run-twice measurement on them stays a measurement and only
    the repetitions after it are saved."""

    #: Every intact run seen so far, by key; shared by all targets.
    memo: dict[str, runner.RunResult] = {}

    def __init__(self, target: str):
        self.target = os.path.realpath(target)
        self.cap: float | None = None
        self.cover_out: str | None = None
        self.longest = self.peak_mb = 0.0
        self.learning = True
        self.reset()

    def reset(self) -> None:
        """Before each mutant: nothing counted, nothing of the last
        mutant's runs remembered."""
        self.runs = self.timeouts = self.crashes = self.bloats = 0
        self.twice: dict[str, tuple[bool, runner.RunResult]] = {}

    def __call__(self, argv, *, stdin=b"", wall_s=60.0, cwd=None):
        mine = (len(argv) > 1 and argv[0] == sys.executable
                and os.path.realpath(argv[1]) == self.target)
        key = _run_key(argv, stdin)
        if key in self.memo and not (mine and self.cover_out):
            res = self.memo[key]
            self.longest = max(self.longest, res.wall_s)
            return res
        if not self.learning:
            agreed, res = self.twice.get(key, (False, None))
            if agreed:
                return res
        if mine and self.cover_out:
            argv = [argv[0], COVER, self.cover_out, *argv[1:]]
        if self.cap is not None:
            wall_s = min(wall_s, self.cap)
        res, peak, bloated = _sealed(argv, stdin, wall_s, cwd)
        if self.learning:
            self.memo[key] = res
        else:
            first = self.twice.get(key)
            self.twice[key] = (
                first is not None and not res.timed_out
                and (first[1].out, first[1].rc) == (res.out, res.rc), res)
        self.longest = max(self.longest, res.wall_s)
        self.peak_mb = max(self.peak_mb, peak)
        if mine:
            self.runs += 1
            self.bloats += bloated
            self.timeouts += res.timed_out and not bloated
            self.crashes += b"Traceback" in res.err
        return res


# -- staging ------------------------------------------------------------------

def stage(reg_root: str, t: dict, scratch: str) -> str:
    """A scratch registry: every entry a link to the real one, the
    entry under test a copy that may be written. Returns the copy."""
    staged = ""
    for sub in SUBS:
        os.makedirs(os.path.join(scratch, "reg", sub))
        base = os.path.join(reg_root, sub)
        for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            real = os.path.join(base, name)
            link = os.path.join(scratch, "reg", sub, name)
            if os.path.realpath(real) == os.path.realpath(
                    t["manifest"]["_dir"]):
                shutil.copytree(real, link, ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc"))
                staged = link
            else:
                os.symlink(os.path.abspath(real), link)
    return staged


def fresh_tmp(scratch: str) -> None:
    """The gate's temporary files go to a directory of ours, emptied
    between mutants."""
    tmp = os.path.join(scratch, "tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    tempfile.tempdir = tmp


#: Progress goes to stderr when the package is run as a program.
VERBOSE = False


def say(text: str) -> None:
    if VERBOSE:
        sys.stderr.write(text + "\n")


def append(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def done(path: str, entry: str, file: str, seed: int) -> set:
    done = set()
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if (r.get("entry"), r.get("file"), r.get("seed")) == (
                        entry, file, seed) and "node" in r:
                    done.add((r["node"], r["alt"]))
    return done
