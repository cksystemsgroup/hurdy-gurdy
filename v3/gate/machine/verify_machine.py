"""Gate a btor2-machine realization (whole-machine equivalence to Sail).

Wraps ``tools.sail_btor2_machine.verify``; on ``green`` flips the group's
``equivalence`` to GREEN and publishes the realization. Until then, any
pair's ``machine_tool`` path stays unavailable (merge policy refuses to rely
on an un-gated realization).

This now does the real work: load the group, generate the BTOR2 machine,
discharge the per-instruction F3 lemmas with z3, cross-validate the reference
against the Sail emulator, subtract IDF, and return the real
``MachineFidelityReport``. It does NOT manufacture green: ``green`` stays
False while the fetch/decode harness lemma is undischarged (``harness_lemma_ok``
is None), which is the honest state of the RV64I/M ALU slice.
"""

from __future__ import annotations

from pathlib import Path

from gurdy.core.report import MachineFidelityReport

SEMANTICS = Path(__file__).resolve().parents[2] / "semantics"


def gate_machine(group: str, *, cross_check: bool = True) -> MachineFidelityReport:
    """Run the whole-machine equivalence gate for one source-semantics group.

    Real for the ``sail-riscv`` group (the only group with a btor2-machine
    realization). Generates the model, runs the z3 lemmas + the Sail
    cross-check, and returns the report. ``green`` reflects ground truth.
    """
    group_dir = SEMANTICS / group
    if group != "sail-riscv" or not group_dir.is_dir():
        # no btor2-machine realization for this group
        return MachineFidelityReport(realization=f"{group}@btor2-machine")

    from tools.sail_btor2_machine.generate import generate
    from tools.sail_btor2_machine.harness import ISAConfig
    from tools.sail_btor2_machine.verify import verify

    out_dir = group_dir / "realizations" / "btor2-machine"
    sail_model_dir = group_dir / "model"          # vendored Sail source (pinned)

    machine = generate(sail_model_dir, ISAConfig(isa="rv64"), out_dir=out_dir)
    report = verify(machine, sail_model_dir, idf_allowlist=_load_idf(group_dir),
                    cross_check=cross_check)

    if report.green:
        _publish_green(group_dir)
    return report


def _load_idf(group_dir: Path) -> list[str]:
    """Best-effort load of the group's IDF allowlist ids (conservative: empty
    on any problem — IDF only ever *subtracts* divergences)."""
    path = group_dir / "idf_allowlist.yaml"
    if not path.is_file():
        return []
    try:
        import yaml
        data = yaml.safe_load(path.read_text()) or {}
        return [p.get("id", "") for p in data.get("points", [])]
    except Exception:
        return []


def _publish_green(group_dir: Path) -> None:
    """Flip GROUP.yaml's btor2-machine equivalence to GREEN. Only reached when
    the report is genuinely green (harness lemma discharged + reference pinned
    to Sail + all lemmas proven). Conservative textual flip; no-op if already
    GREEN or the marker is absent."""
    gy = group_dir / "GROUP.yaml"
    if not gy.is_file():
        return
    text = gy.read_text()
    if "equivalence: PARTIAL" in text:
        gy.write_text(text.replace("equivalence: PARTIAL", "equivalence: GREEN", 1))
