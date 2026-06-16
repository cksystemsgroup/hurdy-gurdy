"""Cross-validate the symbolic reference against the real Sail emulator.

The F3 lowering lemmas (``verify.py``) prove the BTOR2 execute fragments equal
``semantics/sail-riscv/reference_rv64.py`` *for all inputs*. That reference is
spec-derived; on its own it "stands in for Sail". THIS module closes that gap:
for each instruction, over a set of random + corner inputs, it asserts the
reference computes the SAME result the pinned Sail emulator produces. The
two-step chain is then:

    Sail emulator  --(this cross-check, concrete F1)-->  reference_rv64.py
    reference_rv64 --(z3 QF_BV lemmas, symbolic F3)-->   BTOR2 model

so the reference is no longer unaudited — it is pinned to real Sail — while the
all-inputs F3 proofs already in place are kept.

To stay fast, all input cases for one instruction are batched into a single
assembled program (each case writes a distinct destination register), so the
whole 43-instruction audit is ~43 emulator invocations, not hundreds.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import z3

from tools.sail_btor2_machine.isa import rv64_alu as ISA
from tools.sail_btor2_machine.verify import _load_reference, _reference_result

MASK64 = (1 << 64) - 1
INT_MIN = 1 << 63
INT_MAX = (1 << 63) - 1


_ORACLE = None


def _load_oracle():
    """Import the Sail emulator oracle by path (semantics/ is not a package).

    Cached: every caller must share ONE module object, otherwise each call would
    mint a fresh ``SailUnavailable``/``ToolchainUnavailable`` class and an
    ``except oracle.SailUnavailable`` in one function would silently fail to
    catch the exception raised via a *different* ``_load_oracle()`` result (e.g.
    ``cross_check`` catching what ``collect_records`` raises). That only bites
    when Sail is actually absent, so it escaped local runs (Sail present)."""
    global _ORACLE
    if _ORACLE is not None:
        return _ORACLE
    path = (
        Path(__file__).resolve().parents[2]
        / "semantics" / "sail-riscv" / "realizations" / "emulator" / "oracle.py"
    )
    spec = importlib.util.spec_from_file_location("sail_emulator_oracle", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sail_emulator_oracle"] = mod          # register BEFORE exec
    spec.loader.exec_module(mod)
    _ORACLE = mod
    return mod


# ---------------------------------------------------------------------------
# concrete evaluation of the symbolic reference
# ---------------------------------------------------------------------------

def _concrete_reference(ref, spec: ISA.InstrSpec, env_vals: dict[str, int]) -> int:
    """Evaluate reference_rv64 for one instruction on concrete inputs."""
    env = {k: z3.BitVecVal(v & MASK64, 64) for k, v in env_vals.items()}
    result = _reference_result(ref, spec, env)
    return z3.simplify(result).as_long() & MASK64


# ---------------------------------------------------------------------------
# input generation (deterministic, seeded)
# ---------------------------------------------------------------------------

_CORNERS = [0, 1, 2, MASK64, INT_MIN, INT_MAX,
            0x00000000FFFFFFFF, 0xFFFFFFFF00000000, 1 << 31, 0x7FFFFFFF]


def _signed(v: int) -> int:
    v &= MASK64
    return v - (1 << 64) if v >= INT_MIN else v


@dataclass
class Case:
    """One input case for one instruction, with the reference's expected out."""

    env_vals: dict          # keys the reference dispatch needs (a/b/uimm/pc)
    asm: str                # the single target instruction, writing dest reg
    dest: int               # destination GPR index whose value to read back
    expected: int           # reference result (64-bit), filled in by cross_check


def _gen_cases(spec: ISA.InstrSpec, rng: random.Random, n_random: int,
               dest_pool: list[int]) -> list[Case]:
    """Build the input cases for one instruction, each assigned a dest reg."""
    name = spec.name
    cases: list[Case] = []

    def reg(i):
        return dest_pool[i]

    if spec.kind == "u-type":
        # 20-bit U-immediate. AUIPC's pc is supplied by cross_check (it places
        # the u-type ops contiguously from RAM_BASE so pc is predictable).
        imms = [0, 1, 0xFFFFF, 0x80000, 0x7FFFF] + [rng.randrange(1 << 20) for _ in range(n_random)]
        for k, imm20 in enumerate(imms):
            d = reg(k)
            cases.append(Case({"imm20": imm20}, f"  {name.lower()} x{d}, {imm20}\n", d, 0))
        return cases

    if spec.kind == "reg-reg":
        pairs = [(0, 0), (1, 1), (INT_MAX, 1), (MASK64, MASK64),
                 (INT_MIN, MASK64), (INT_MIN, 1), (123456789, 0),
                 (0xDEADBEEF, 0xFFFF), (1 << 40, 7)]
        pairs += [(rng.getrandbits(64), rng.getrandbits(64)) for _ in range(n_random)]
        for k, (a, b) in enumerate(pairs[:len(dest_pool)]):
            d = reg(k)
            asm = (f"  li a0, {_signed(a)}\n  li a1, {_signed(b)}\n"
                   f"  {name.lower()} x{d}, a0, a1\n")
            cases.append(Case({"a": a, "b": b}, asm, d, 0))
        return cases

    if spec.kind == "reg-imm":
        if name in ("SLLI", "SRLI", "SRAI"):           # 6-bit shamt
            shamts = [0, 1, 31, 32, 63]
            built = [(0, 0), (1, 63), (MASK64, 1), (INT_MIN, 63), (0xDEADBEEFCAFEF00D, 32)]
            built += [(rng.getrandbits(64), rng.choice(shamts)) for _ in range(n_random)]
            for k, (a, sh) in enumerate(built[:len(dest_pool)]):
                d = reg(k)
                asm = f"  li a0, {_signed(a)}\n  {name.lower()} x{d}, a0, {sh}\n"
                cases.append(Case({"a": a, "b": sh}, asm, d, 0))
            return cases
        if name in ("SLLIW", "SRLIW", "SRAIW"):        # 5-bit shamt
            built = [(0, 0), (1, 31), (MASK64, 1), (INT_MIN, 31), (0x00000000FFFFFFFF, 16)]
            built += [(rng.getrandbits(64), rng.randrange(32)) for _ in range(n_random)]
            for k, (a, sh) in enumerate(built[:len(dest_pool)]):
                d = reg(k)
                asm = f"  li a0, {_signed(a)}\n  {name.lower()} x{d}, a0, {sh}\n"
                cases.append(Case({"a": a, "b": sh}, asm, d, 0))
            return cases
        # arithmetic 12-bit immediate (ADDI/SLTI/SLTIU/XORI/ORI/ANDI/ADDIW)
        built = [(0, 0), (1, -1), (MASK64, 1), (INT_MIN, -2048), (INT_MAX, 2047),
                 (0x00000000FFFFFFFF, -1)]
        built += [(rng.getrandbits(64), rng.randrange(-2048, 2048)) for _ in range(n_random)]
        for k, (a, imm) in enumerate(built[:len(dest_pool)]):
            d = reg(k)
            asm = f"  li a0, {_signed(a)}\n  {name.lower()} x{d}, a0, {imm}\n"
            # reference operand b is the sign-extended 12-bit immediate
            cases.append(Case({"a": a, "b": imm & MASK64}, asm, d, 0))
        return cases

    raise ValueError(f"unhandled kind {spec.kind} for {name}")


# ---------------------------------------------------------------------------
# the cross-check
# ---------------------------------------------------------------------------

@dataclass
class Record:
    """One audited case: what the reference computed and what Sail produced."""

    instance_id: str
    mnemonic: str
    inputs: dict
    reference: int
    sail: int

    @property
    def agree(self) -> bool:
        return (self.reference & MASK64) == (self.sail & MASK64)

    def describe(self) -> str:
        return (f"{self.mnemonic}: inputs={_fmt(self.inputs)} "
                f"reference=0x{self.reference:016x} sail=0x{self.sail:016x}")


@dataclass
class CrossResult:
    ok: bool = True
    instructions_checked: int = 0
    cases_checked: int = 0
    divergences: list[str] = field(default_factory=list)   # human-readable
    skipped_reason: str | None = None


# destination-register pool: x12..x31 (avoids x0/ra/sp, the li scratch a0/a1 =
# x10/x11, and the halt epilogue's t0/t1 = x5/x6).
_DEST_POOL = list(range(12, 32))


def _instance_id(mnemonic: str, inputs: dict) -> str:
    body = ",".join(f"{k}={inputs[k] & MASK64:#x}" for k in sorted(inputs))
    return f"{mnemonic}[{body}]"


def collect_records(*, n_random: int = 3, seed: int = 0xC0FFEE,
                    instrs: list[str] | None = None) -> list[Record]:
    """Run every instruction's cases through reference + Sail, returning one
    ``Record`` per case (reference result vs Sail result). Raises
    ``SailUnavailable`` / ``ToolchainUnavailable`` if the emulator/toolchain is
    missing. This is the shared engine under both ``cross_check`` (Step 4a) and
    the gate's F1 differential (Step 3)."""
    oracle = _load_oracle()
    oracle.sail_binary()                       # raises SailUnavailable if absent

    ref = _load_reference()
    rng = random.Random(seed)
    specs = ISA.ALL_SPECS if instrs is None else [ISA.SPEC_BY_NAME[n] for n in instrs]

    records: list[Record] = []
    for spec in specs:
        cases = _gen_cases(spec, rng, n_random, _DEST_POOL)
        if not cases:
            continue
        # AUIPC: place the u-type ops contiguously from RAM_BASE so each one's
        # pc is RAM_BASE + 4*index; feed that pc to the reference.
        body = "".join(c.asm for c in cases)
        for k, c in enumerate(cases):
            if spec.name == "AUIPC":
                c.env_vals = {"pc": oracle.RAM_BASE + 4 * k, "uimm": _uimm(c.env_vals["imm20"])}
            elif spec.name == "LUI":
                c.env_vals = {"uimm": _uimm(c.env_vals["imm20"])}
            c.expected = _concrete_reference(ref, spec, c.env_vals)

        elf = oracle.assemble(body)            # raises ToolchainUnavailable
        projs = oracle.run(elf, max_steps=len(cases) * 12 + 8)
        observed = projs[-1].regs if projs else {}
        for c in cases:
            records.append(Record(
                instance_id=_instance_id(spec.name, c.env_vals),
                mnemonic=spec.name, inputs=dict(c.env_vals),
                reference=c.expected, sail=observed.get(c.dest, 0) & MASK64,
            ))
    return records


def cross_check(*, n_random: int = 3, seed: int = 0xC0FFEE,
                instrs: list[str] | None = None) -> CrossResult:
    """Audit reference_rv64 against the Sail emulator. Returns a CrossResult;
    ``ok`` is True iff every case agreed (or there was nothing to check).
    If Sail/toolchain is unavailable, returns ok=False with skipped_reason."""
    oracle = _load_oracle()
    try:
        records = collect_records(n_random=n_random, seed=seed, instrs=instrs)
    except (oracle.SailUnavailable, oracle.ToolchainUnavailable) as e:
        return CrossResult(ok=False, skipped_reason=str(e))

    res = CrossResult()
    res.instructions_checked = len({r.mnemonic for r in records})
    for r in records:
        res.cases_checked += 1
        if not r.agree:
            res.ok = False
            res.divergences.append(r.describe())
    return res


@dataclass
class DecodeResult:
    ok: bool = True
    steps_checked: int = 0
    divergences: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


def decode_vs_sail(*, num_programs: int = 6, seq_len: int = 12, seed: int = 0xD3C0DE) -> DecodeResult:
    """Validate the MACHINE DECODER against real Sail-emitted instruction words.

    Runs random programs (li-materialized operands exercise lui/addi/addiw/slli
    decode; reg-reg ALU ops exercise the rest), and for every instruction Sail
    executes that the machine recognizes, checks the machine's
    decode+execute+writeback matches Sail's actual register write. This closes
    the residual risk that the symbolic harness lemma can't: a *shared* decode
    misreading in both the machine and the reference transcription. Sail is the
    fully-independent third implementation."""
    from tools.sail_btor2_machine import control

    oracle = _load_oracle()
    try:
        oracle.sail_binary()
    except oracle.SailUnavailable as e:
        return DecodeResult(ok=False, skipped_reason=str(e))

    rng = random.Random(seed)
    alu = [s.name.lower() for s in ISA.ALL_SPECS if ISA.SPEC_BY_NAME[s.name].kind == "reg-reg"]
    res = DecodeResult()
    for _p in range(num_programs):
        srcs = list(range(5, 16))              # x5..x15 hold random operands
        body = "".join(f"  li x{r}, {_signed(rng.getrandbits(64))}\n" for r in srcs)
        for _i in range(seq_len):
            op = rng.choice(alu)
            rd, rs1, rs2 = rng.randrange(5, 28), rng.choice(srcs), rng.choice(srcs)
            body += f"  {op} x{rd}, x{rs1}, x{rs2}\n"
        try:
            elf = oracle.assemble(body)
        except oracle.ToolchainUnavailable as e:
            return DecodeResult(ok=False, skipped_reason=str(e))
        projs = oracle.run(elf, max_steps=len(srcs) * 12 + seq_len + 8)

        prev = {i: 0 for i in range(32)}
        for p in projs:
            out = control.concrete_step(p.instr, prev, p.pc)
            if out is not None:                # an in-slice instruction
                rd, value, _npc = out
                res.steps_checked += 1
                got = p.regs.get(rd, 0) & MASK64
                if rd != 0 and got != value:
                    res.ok = False
                    res.divergences.append(
                        f"iw=0x{p.instr:08x} @pc=0x{p.pc:x}: machine x{rd}=0x{value:016x} "
                        f"sail x{rd}=0x{got:016x}")
            prev = p.regs
    return res


def _uimm(imm20: int) -> int:
    """The 64-bit value LUI/AUIPC place: (imm20 << 12), sign-extended from 32."""
    v32 = (imm20 << 12) & 0xFFFFFFFF
    if v32 & 0x80000000:
        return (v32 | 0xFFFFFFFF00000000) & MASK64
    return v32


def _fmt(env_vals: dict) -> str:
    return "{" + ", ".join(f"{k}=0x{v & MASK64:x}" for k, v in env_vals.items()) + "}"
