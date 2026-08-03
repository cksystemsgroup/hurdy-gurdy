"""Certifaiger witness circuits — the AIGER certificate route for an
**unbounded** ``unreachable`` (issue #2 route (b), the checker-side
alternative to ``solvers/invariant.py``'s SMT re-discharge; SOLVERS.md §5;
DOCKER.md's certifaiger layer is the in-image checker).

The construction: bit-blast the BTOR2 system into an AIGER model
(``languages/btor2/aiger.py``), compile pono's ``--show-invar`` inductive
invariant — one per ``bad`` property, conjoined — into the same graph, and
emit a *witness circuit*: identical inputs, latches, resets, next
functions and constraints (an explicit identity mapping in the symbol
table), with the invariant as its sole property. Certifaiger's safety-side
obligations then reduce exactly to what pono proved: Reset/Transition are
syntactic tautologies (the circuits share the structure), Safety is
``inv ∧ C → ¬bad``, Base is ``init ∧ C → inv``, Inductive is
``inv ∧ C ∧ T ∧ C' → inv'`` — each discharged by certifaiger's own SAT
harness (kissat), a toolchain lineage-disjoint from pono's declared
(pono, smt-switch, bitwuzla, boolector).

Fail-safe discipline as everywhere in this layer: an invariant term
outside the compiler's grammar, an unsupported BTOR2 construct, or a
checker rejection can only fail to certify — never fake a certificate.
What remains in the TCB when the check passes is recorded: this module's
own BTOR2→AIGER bit-blast (the same standing the bridge's operator
mapping has under invariant re-discharge), certifaiger's witness-format
reduction, and the SAT solver.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any

from ..core.errors import Unsupported
from ..languages.btor2.aiger import (
    FALSE,
    TRUE,
    Blasted,
    bitblast,
    v_const,
    v_eq,
    v_mul,
    v_not,
    v_shift,
    v_slt,
    v_sub,
    v_udivrem,
    v_ult,
)
from ..languages.btor2.aiger import v_add as _v_add
from ..languages.btor2.aiger import v_bitwise as _v_bitwise
from ..languages.btor2.model import from_text
from .invariant import extract_invariant
from .pono_btor2 import UNBOUNDED_WALL_S


class CertifaigerUnavailable(RuntimeError):
    pass


def find_certifaiger() -> str | None:
    return os.environ.get("CERTIFAIGER_CHECK") or shutil.which("certifaiger-check")


@dataclass(frozen=True)
class AigerCertResult:
    ok: bool                     # checker validated the witness circuit
    tier: str | None             # "proved" | None
    invariant: str | None        # the certified term (single-property runs)
    checker_ok: bool | None      # None: never reached the checker
    model_aag: str | None = None
    witness_aag: str | None = None
    tcb: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)


# ------------------------------------------------------- invariant → AIG

def _tokenize(term: str) -> list[str]:
    return term.replace("(", " ( ").replace(")", " ) ").split()


def _parse(tokens: list[str]) -> Any:
    def rec(i: int) -> tuple[Any, int]:
        if tokens[i] == "(":
            out: list[Any] = []
            i += 1
            while i < len(tokens) and tokens[i] != ")":
                node, i = rec(i)
                out.append(node)
            if i >= len(tokens):
                raise Unsupported("certifaiger", "unbalanced invariant term")
            return out, i + 1
        return tokens[i], i + 1

    if not tokens:
        raise Unsupported("certifaiger", "empty invariant term")
    node, i = rec(0)
    if i != len(tokens):
        raise Unsupported("certifaiger", "trailing tokens in invariant term")
    return node


#: pono names BTOR2 terms by node id — the ``frame_invariant`` discipline:
#: an unmapped name raises, never becomes an implicitly-free variable.
_PONO_NAME = re.compile(r"^(state|input)(\d+)$")

_NARY_BV = {"bvand": "and", "bvor": "or", "bvxor": "xor"}
_CMP = {"bvult", "bvule", "bvugt", "bvuge", "bvslt", "bvsle", "bvsgt", "bvsge"}
_SHIFT = {"bvshl": "sll", "bvlshr": "srl", "bvashr": "sra"}


class _InvariantCompiler:
    """Compile an SMT-LIB invariant term over ``state<id>``/``input<id>``
    names into a literal of the blasted system's graph. Grammar outside the
    supported core hard-aborts with ``Unsupported`` — fail-safe."""

    def __init__(self, blasted: Blasted) -> None:
        self.b = blasted
        self.aig = blasted.aig
        self.sys = blasted.system

    def compile_bool(self, term: str) -> int:
        vec = self._term(_parse(_tokenize(term)), {})
        if len(vec) != 1:
            raise Unsupported("certifaiger",
                              f"invariant is {len(vec)} bits wide, not boolean")
        return vec[0]

    def _bool(self, vec: list[int], what: str) -> int:
        if len(vec) != 1:
            raise Unsupported("certifaiger", f"{what} needs boolean operands")
        return vec[0]

    def _same_width(self, args: list[list[int]], what: str) -> None:
        if len({len(a) for a in args}) > 1:
            raise Unsupported("certifaiger", f"width mismatch under {what}")

    def _term(self, t: Any, env: dict[str, list[int]]) -> list[int]:
        aig = self.aig
        if isinstance(t, str):
            if t in env:
                return env[t]
            m = _PONO_NAME.match(t)
            if m:
                kind, nid = m.group(1), int(m.group(2))
                node = self.sys.nodes.get(nid)
                if node is None or node.op != kind:
                    raise Unsupported("certifaiger",
                                      f"invariant names unknown node {t}")
                return (self.b.state_bits if kind == "state"
                        else self.b.input_bits)[nid]
            if t == "true":
                return [TRUE]
            if t == "false":
                return [FALSE]
            if t.startswith("#b"):
                return v_const(len(t) - 2, int(t[2:], 2))
            if t.startswith("#x"):
                return v_const(4 * (len(t) - 2), int(t[2:], 16))
            raise Unsupported("certifaiger", f"invariant atom {t!r}")
        if not t:
            raise Unsupported("certifaiger", "empty application")
        head = t[0]
        if isinstance(head, list):  # ((_ extract hi lo) x) and friends
            if len(head) >= 2 and head[0] == "_":
                if head[1] == "extract":
                    hi, lo = int(head[2]), int(head[3])
                    v = self._term(t[1], env)
                    if not 0 <= lo <= hi < len(v):
                        raise Unsupported("certifaiger",
                                          f"extract [{hi}:{lo}] out of range")
                    return v[lo:hi + 1]
                if head[1] in ("zero_extend", "sign_extend"):
                    n, v = int(head[2]), self._term(t[1], env)
                    fill = v[-1] if head[1] == "sign_extend" else FALSE
                    return v + [fill] * n
            raise Unsupported("certifaiger", f"invariant op {head!r}")
        if head == "_":  # (_ bvN w)
            if len(t) == 3 and t[1].startswith("bv"):
                return v_const(int(t[2]), int(t[1][2:]))
            raise Unsupported("certifaiger", f"indexed term {t!r}")
        if head == "let":  # parallel let, bindings read the outer scope
            inner = dict(env)
            for pair in t[1]:
                inner[pair[0]] = self._term(pair[1], env)
            return self._term(t[2], inner)

        args = [self._term(x, env) for x in t[1:]]
        if head in ("and", "or"):
            acc = TRUE if head == "and" else FALSE
            fn = aig.and_ if head == "and" else aig.or_
            for a in args:
                acc = fn(acc, self._bool(a, head))
            return [acc]
        if head == "not":
            return [self._bool(args[0], head) ^ 1]
        if head == "=>":
            acc = self._bool(args[-1], head)
            for a in reversed(args[:-1]):
                acc = aig.or_(self._bool(a, head) ^ 1, acc)
            return [acc]
        if head == "xor":
            acc = FALSE
            for a in args:
                acc = aig.xor_(acc, self._bool(a, head))
            return [acc]
        if head in ("=", "bvcomp", "distinct"):
            self._same_width(args, head)
            if head == "distinct":
                acc = TRUE
                for i in range(len(args)):
                    for j in range(i + 1, len(args)):
                        acc = aig.and_(acc, v_eq(aig, args[i], args[j]) ^ 1)
                return [acc]
            acc = TRUE
            for a, c in zip(args, args[1:]):
                acc = aig.and_(acc, v_eq(aig, a, c))
            return [acc]
        if head == "ite":
            c = self._bool(args[0], head)
            self._same_width(args[1:], head)
            return [aig.ite_(c, x, y) for x, y in zip(args[1], args[2])]
        if head in _NARY_BV:
            self._same_width(args, head)
            acc = args[0]
            for a in args[1:]:
                acc = _v_bitwise(aig, _NARY_BV[head], acc, a)
            return acc
        if head == "bvnot":
            return v_not(args[0])
        if head == "bvneg":
            return _v_add(aig, v_not(args[0]),
                          v_const(len(args[0]), 0), cin=TRUE)
        if head in ("bvadd", "bvmul"):
            self._same_width(args, head)
            acc = args[0]
            for a in args[1:]:
                acc = (_v_add(aig, acc, a) if head == "bvadd"
                       else v_mul(aig, acc, a))
            return acc
        if head in ("bvsub", "bvudiv", "bvurem"):
            self._same_width(args, head)
            if head == "bvsub":
                return v_sub(aig, args[0], args[1])
            quot, rem = v_udivrem(aig, args[0], args[1])
            return quot if head == "bvudiv" else rem
        if head in _CMP:
            self._same_width(args, head)
            a, b = args
            if head in ("bvugt", "bvuge", "bvsgt", "bvsge"):
                a, b = b, a
            cmp = v_slt if head[2] == "s" else v_ult
            if head in ("bvult", "bvugt", "bvslt", "bvsgt"):
                return [cmp(aig, a, b)]
            return [cmp(aig, b, a) ^ 1]  # a <= b as not (b < a)
        if head in _SHIFT:
            self._same_width(args, head)
            return v_shift(aig, _SHIFT[head], args[0], args[1])
        if head == "concat":
            out: list[int] = []
            for a in reversed(args):  # first operand is the high part
                out += a
            return out
        raise Unsupported("certifaiger", f"invariant op {head!r}")


# ------------------------------------------------------------- emission

def emit_certificate(system: Any, invariants: list[str],
                     *, model_name: str = "model.aag") -> tuple[str, str]:
    """Bit-blast the system and emit the ``(model, witness)`` AIGER pair:
    the model with its own ``bad``/``constraint`` sections, the witness
    with the conjoined invariant as its sole property and an explicit
    identity mapping for every input and latch. Node ids must be the ones
    pono saw — pass the same BTOR2 text ``extract_invariant`` ran on."""
    blasted = bitblast(system)
    aig = blasted.aig
    if not blasted.bads:
        raise ValueError("system declares no bad property — nothing to certify")
    model = aig.to_aag(
        bads=blasted.bads, constraints=blasted.constraints,
        comment="MODEL bit-blasted from BTOR2 by hurdy-gurdy "
                "(languages/btor2/aiger.py)")
    comp = _InvariantCompiler(blasted)
    inv = TRUE
    for term in invariants:
        inv = aig.and_(inv, comp.compile_bool(term))
    witness = aig.to_aag(
        bads=[inv ^ 1], constraints=blasted.constraints,
        input_names=[f"= {lit}" for lit, _sym in aig.inputs],
        latch_names=[f"= {latch.lit}" for latch in aig.latches],
        comment=f"WITNESS b0 {model_name} inductive invariant "
                "(pono --show-invar), emitted by hurdy-gurdy "
                "(solvers/certifaiger.py, issue #2 route (b))")
    return model, witness


def check_witness_circuit(model_aag: str, witness_aag: str,
                          *, timeout_s: int = 600) -> tuple[bool, dict]:
    """Run ``certifaiger-check`` on the pair. ``True`` only on exit 0 with
    the harness's own "valid witness" verdict; everything else — an
    obligation going sat, a parse rejection, a missing sub-tool — is a
    recorded failure, never a silent pass."""
    binary = find_certifaiger()
    if not binary:
        raise CertifaigerUnavailable(
            "certifaiger-check not found (set $CERTIFAIGER_CHECK or PATH; "
            "the dev image ships it under /opt/certifaiger/bin)")
    with tempfile.TemporaryDirectory(prefix="certifaiger-") as tmp:
        mpath = os.path.join(tmp, "model.aag")
        wpath = os.path.join(tmp, "witness.aag")
        with open(mpath, "w") as f:
            f.write(model_aag)
        with open(wpath, "w") as f:
            f.write(witness_aag)
        proc = subprocess.run([binary, mpath, wpath], capture_output=True,
                              text=True, timeout=timeout_s)
    out = proc.stdout + proc.stderr
    ok = proc.returncode == 0 and "valid witness" in out
    return ok, {"checker": binary, "checker_exit": proc.returncode,
                "checker_output": out.strip()[-400:]}


# ----------------------------------------------------------- end to end

def certify_unreachable_aiger(system: Any, *, mode: str = "ic3bits",
                              timeout_s: int = UNBOUNDED_WALL_S,
                              check_timeout_s: int = 600) -> AigerCertResult:
    """The end-to-end route: extract pono's invariant for **every** ``bad``
    property (pono is per-property; the unbounded claim is any-bad),
    conjoin them into one witness circuit, and have certifaiger validate
    it. Extraction stops at the first property pono does not prove — the
    walls are declared budgets, not free retries. ``tier`` is ``proved``
    only on a validated check: certifaiger's toolchain (certifaiger,
    aiger, kissat) is lineage-disjoint from pono's declared four."""
    if not isinstance(system, (str, bytes, bytearray)):
        raise Unsupported("certifaiger", "pono extraction needs BTOR2 text")
    text = (system.decode("utf-8")
            if isinstance(system, (bytes, bytearray)) else system)
    bads = from_text(text).bads()
    if not bads:
        raise ValueError("system declares no bad property — nothing to certify")
    prov: dict[str, Any] = {"mode": mode, "props": {}}
    invariants: list[str] = []
    for prop in range(len(bads)):
        inv = extract_invariant(text, mode=mode, prop=prop,
                                timeout_s=timeout_s)
        if inv is None:
            prov["props"][prop] = ("no invariant — pono did not prove unsat; "
                                   "remaining properties not attempted")
            return AigerCertResult(ok=False, tier=None, invariant=None,
                                   checker_ok=None, provenance=prov)
        invariants.append(inv)
        prov["props"][prop] = {"invariant": inv}
    model, witness = emit_certificate(text, invariants)
    ok, cprov = check_witness_circuit(model, witness,
                                      timeout_s=check_timeout_s)
    prov.update(cprov)
    if ok:
        prov["independence_note"] = (
            "certifaiger/aiger/kissat — no overlap with pono's declared "
            "lineage (pono, smt-switch, bitwuzla, boolector); the bit-blast "
            "is this platform's own and stays in the TCB, recorded")
    return AigerCertResult(
        ok=ok, tier="proved" if ok else None,
        invariant=invariants[0] if len(invariants) == 1 else None,
        checker_ok=ok, model_aag=model, witness_aag=witness,
        tcb=(["hurdy-gurdy:btor2-aiger-bitblast",
              "certifaiger:witness-circuit", "kissat:sat"] if ok else []),
        provenance=prov)
