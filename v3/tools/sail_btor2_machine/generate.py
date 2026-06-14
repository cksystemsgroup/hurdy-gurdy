"""Generate a BTOR2 machine model from the RV64 ISA specs (referential agent).

Each instruction's *execute* (a single ``isa.expr.Expr`` tree — the same tree
the verifier proves equivalent to the reference) is lowered to BTOR2 op lines.
The harness (state shape from ``harness.py``) frames them. We emit:

  * ``model.btor2``     — a valid BTOR2 transition system,
  * ``decode_map.json`` — mnemonic -> {opcode,funct3,funct7,...},
  * ``provenance.json`` — mnemonic -> {spec_ref, exec_name, btor2_lines}.

WHAT THE EMITTED MODEL DOES / DOES NOT INCLUDE (read this)
=========================================================
INCLUDED (and proven equivalent to the reference, per ``verify.py``):
  * the fixed harness STATE declarations (pc, regfile array, mem array, csrs
    array, halted), as a BTOR2 ``state``/``init``/``next`` skeleton;
  * one BTOR2 *execute datapath* per instruction: the result bitvector as a
    function of symbolic operand inputs (rs1=a, rs2/imm=b, pc, uimm). These
    fragments are the F3 lemma subjects.

NOT YET INCLUDED (the explicit next slice):
  * a full fetch-from-symbolic-memory + decode-dispatch loop that selects the
    execute fragment from the instruction word and writes back into the
    regfile/pc state. The harness lemma (control == reference step) is
    therefore not yet emitted/proven; ``verify`` reports harness_lemma_ok=None.

So: execute fragments are faithful and machine-checked; the dispatch harness
is a stub. The emission is deterministic.

This is the *referential* agent's tool: it mirrors the reference semantics.
Pair-build agents must not call it during construction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tools.sail_btor2_machine.harness import ISAConfig, SKELETON_STATE
from tools.sail_btor2_machine.isa import expr as E
from tools.sail_btor2_machine.isa import rv64_alu as ISA


@dataclass
class GeneratedMachine:
    realization: str                          # "sail-riscv@btor2-machine"
    model_path: Path | None = None            # model.btor2
    decode_map: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)   # instr -> {spec_ref, btor2_lines}


def _emit_harness_state(bld: E.Btor2Builder, cfg: ISAConfig) -> list[str]:
    """Emit the fixed CPU state skeleton (pc, regfile, mem, csrs, halted).

    Arrays use BTOR2 ``sort array``; ``state`` lines declare the registers.
    init/next for the full dispatch are the next slice, so state is declared
    but its transition is left for the harness lemma stage (documented).
    """
    out: list[str] = []
    s_pc = bld.sort(cfg.xlen)
    s_byte = bld.sort(8)
    s_ridx = bld.sort(cfg.ridx_bits)
    s_csridx = bld.sort(12)
    s_bit = bld.sort(1)

    def array_sort(idx_nid: int, elem_nid: int, label: str) -> int:
        nid = bld._next()
        bld.lines.append(f"{nid} sort array {idx_nid} {elem_nid}  ; {label}")
        return nid

    s_regfile = array_sort(s_ridx, s_pc, "regfile: bv{RIDX} -> bv{XLEN}")
    s_mem = array_sort(s_pc, s_byte, "mem: bv{XLEN} -> bv8")
    s_csrs = array_sort(s_csridx, s_pc, "csrs: bv12 -> bv{XLEN}")

    out.append(f"{bld.emit('state {} pc', s_pc)} ; --skeleton-state pc")
    out.append(f"{bld.emit('state {} regfile', s_regfile)} ; --skeleton-state regfile")
    out.append(f"{bld.emit('state {} mem', s_mem)} ; --skeleton-state mem")
    out.append(f"{bld.emit('state {} csrs', s_csrs)} ; --skeleton-state csrs")
    out.append(f"{bld.emit('state {} halted', s_bit)} ; --skeleton-state halted")
    return out


def generate(sail_model_dir: Path, cfg: ISAConfig, *, out_dir: Path) -> GeneratedMachine:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bld = E.Btor2Builder()

    header = [
        "; BTOR2 rv64 machine model (hurdy-gurdy v3, btor2-machine realization)",
        "; Generated deterministically from tools/sail_btor2_machine/isa/rv64_alu.py.",
        "; Execute fragments are proven == reference_rv64 (see MACHINE_BUILD_LOG.md).",
        "; NOTE: fetch/decode dispatch harness = next slice (execute datapath only).",
    ]

    # 1) fixed harness state skeleton
    _emit_harness_state(bld, cfg)

    # 2) per-instruction execute datapaths (the F3 lemma subjects)
    provenance: dict = {}
    decode_map: dict = {}

    for spec in ISA.ALL_SPECS:
        start = len(bld.lines)
        bld.lines.append(f"; === execute fragment: {spec.name} ({spec.exec_name or spec.name}) ===")
        root = bld.lower(spec.execute)
        bld.lines.append(f"; result of {spec.name} = nid {root}")
        end = len(bld.lines)

        decode_map[spec.name] = {
            "kind": spec.kind,
            "opcode": spec.opcode,
            "funct3": spec.funct3,
            "funct7": spec.funct7,
            "funct7_hi": spec.funct7_hi,
            "exec_name": spec.exec_name or spec.name,
            "result_nid": root,
        }
        provenance[spec.name] = {
            "spec_ref": spec.spec_ref,
            "exec_name": spec.exec_name or spec.name,
            "operands": ISA.operand_vars(spec),
            "btor2_lines": bld.lines[start:end],
        }

    model_text = "\n".join(header + bld.lines) + "\n"
    model_path = out_dir / "model.btor2"
    model_path.write_text(model_text)

    (out_dir / "decode_map.json").write_text(json.dumps(decode_map, indent=2, sort_keys=True))
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True))

    return GeneratedMachine(
        realization="sail-riscv@btor2-machine",
        model_path=model_path,
        decode_map=decode_map,
        provenance=provenance,
    )
