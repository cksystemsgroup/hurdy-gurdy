"""The PureOracle seam — Phase 2 of the automated-scaling rollout
(SCALING.md §12.2, §3).

A pair's two *untrusted* pure functions are its translator ``T`` and its
target-to-source interpreter ``Λ`` (PAIRING.md §5). Everything else the square
needs — the interpreters, the projection, the ``align`` oracle — is trusted and
language-owned. This module factors ``T``/``Λ`` behind a swappable ``PureOracle``
so a grader can run them *without hosting the pair's code in its own process*:

- ``InProcessOracle`` calls them directly — today's behaviour, the reference.
- ``SubprocessOracle`` runs the pair's ``translate``/``lift`` in a **separate,
  long-lived child process**. The grader (parent) is trusted; it pickles the
  *input* to the child (fine — the child is the untrusted one), but the child
  returns results in a **safe wire format** the parent parses defensively —
  raw bytes for ``translate``, JSON for ``lift`` — so **the parent never
  unpickles data from untrusted code** (the §3.3 defensive-parse rule).

Because a square is a pure function of ``(T, Λ, I_s, I_t, π, program)``, two
backends that agree on ``T`` and ``Λ`` byte-for-byte agree on every square
verdict — which is what ``tests/test_pure_oracle.py`` proves over the current
pairs, changing no measured number.

**Scope of this phase.** Lands the seam, both backends, and the safe channel —
the property that untrusted pair code runs outside the grader's process and
cannot hand it executable data. OS-level isolation of the child
(filesystem/network/seccomp, per §3.3) and making the grader authoritative over
a pair's own ``square()`` are the next hardening steps.
"""

from __future__ import annotations

import json
import pickle
import struct
import subprocess
import sys
from typing import Any, Protocol

from .registry import Pair
from .types import Trace


class PureOracle(Protocol):
    def translate(self, program: Any) -> bytes: ...
    def lift(self, trace: Trace) -> Trace: ...
    def close(self) -> None: ...


class InProcessOracle:
    """The reference backend: call the pair's pure functions directly."""

    def __init__(self, translate_fn: Any, lift_fn: Any) -> None:
        self._translate = translate_fn
        self._lift = lift_fn

    def translate(self, program: Any) -> bytes:
        return bytes(self._translate(program))

    def lift(self, trace: Trace) -> Trace:
        return self._lift(trace)

    def close(self) -> None:
        pass


# --- framed binary protocol (length-prefixed frames both directions) --------

def _write_frame(stream: Any, payload: bytes) -> None:
    stream.write(struct.pack(">I", len(payload)))
    stream.write(payload)
    stream.flush()


def _read_frame(stream: Any) -> bytes | None:
    header = stream.read(4)
    if not header or len(header) < 4:
        return None
    (n,) = struct.unpack(">I", header)
    buf = stream.read(n)
    if len(buf) < n:
        return None
    return buf


class SubprocessOracle:
    """Run the pair's ``translate``/``lift`` in a long-lived child process.

    The parent sends ``(op, pickle(arg))``; the child returns
    ``(status, payload)`` where ``payload`` is raw bytes (``translate``) or JSON
    (``lift``) — never a pickle. The parent parses it defensively, so untrusted
    child output can never execute in the grader."""

    def __init__(self, pair_id: str) -> None:
        self.pair_id = pair_id
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "gurdy.core.pure_oracle", "serve", pair_id],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )

    def _call(self, op: bytes, arg: Any) -> bytes:
        assert self._proc.stdin and self._proc.stdout
        _write_frame(self._proc.stdin, op)
        _write_frame(self._proc.stdin, pickle.dumps(arg))
        status = _read_frame(self._proc.stdout)
        payload = _read_frame(self._proc.stdout)
        if status is None or payload is None:
            raise RuntimeError(f"pure-oracle child for {self.pair_id} died")
        if status != b"ok":
            raise RuntimeError(f"{self.pair_id}.{op.decode()}: "
                               f"{payload.decode('utf-8', 'replace')}")
        return payload

    def translate(self, program: Any) -> bytes:
        return self._call(b"translate", program)      # raw bytes, safe

    def lift(self, trace: Trace) -> Trace:
        return json.loads(self._call(b"lift", trace))  # JSON, safe

    def close(self) -> None:
        proc = self._proc
        if proc.stdin and not proc.stdin.closed:
            try:
                proc.stdin.close()          # EOF → child's serve loop returns
            except Exception:
                pass
        if proc.poll() is None:
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
                proc.wait()
        if proc.stdout and not proc.stdout.closed:
            proc.stdout.close()             # release the read pipe (no FD leak)

    def __enter__(self) -> "SubprocessOracle":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def for_pair(pair: Pair, backend: str = "inproc") -> PureOracle:
    """Build a PureOracle for a registered pair. ``backend`` is ``"inproc"``
    (reference) or ``"subprocess"`` (out-of-process, safe channel)."""
    if backend == "inproc":
        return InProcessOracle(pair.translator, pair.target_to_source)
    if backend == "subprocess":
        return SubprocessOracle(pair.id)
    raise ValueError(f"unknown PureOracle backend: {backend!r}")


# --- the child server -------------------------------------------------------

def _serve(pair_id: str) -> int:
    """Child entry point: import only this pair's pure functions and answer
    framed ``translate``/``lift`` requests until stdin closes."""
    import importlib

    mod = importlib.import_module(f"gurdy.pairs.{pair_id.replace('-', '_')}")
    translate_fn = mod.translate
    lift_fn = mod.lift

    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        op = _read_frame(stdin)
        if op is None:
            return 0
        raw = _read_frame(stdin)
        if raw is None:
            return 0
        try:
            arg = pickle.loads(raw)                 # from the trusted parent
            if op == b"translate":
                payload = bytes(translate_fn(arg))  # raw bytes back
            elif op == b"lift":
                payload = json.dumps(lift_fn(arg)).encode()
            else:
                raise ValueError(f"unknown op {op!r}")
            _write_frame(stdout, b"ok")
            _write_frame(stdout, payload)
        except Exception as exc:  # noqa: BLE001  (report, don't crash the loop)
            _write_frame(stdout, b"err")
            _write_frame(stdout, f"{type(exc).__name__}: {exc}".encode())


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "serve":
        return _serve(argv[1])
    print("usage: python -m gurdy.core.pure_oracle serve <pair-id>",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
