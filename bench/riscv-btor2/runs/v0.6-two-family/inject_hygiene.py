import json
from pathlib import Path
from datetime import datetime, timezone

det = json.load(open('runs/v0.6-two-family/determinism_report.json'))
now = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

leakage = {
    "schema_in_training_data": "plausible",
    "corpus_in_training_data": "plausible",
    "condition_a_handicapped": False,
    "assessment": (
        "The pair's SCHEMA.md and the task corpus both live in the public "
        "repo (christophkirsch/hurdy-gurdy, whose URL the B/C prompts cite), "
        "so for models whose training cutoff postdates publication both are "
        "plausibly in-distribution. This is moot for conditions B/C, which "
        "are handed the schema anyway."
    ),
    "condition_a_mitigation": (
        "Condition A is NOT handicapped by SCHEMA.md leakage: the schema "
        "documents the RV64->BTOR2 *translation*, not RV64 semantics, which "
        "is all condition A needs and is standard, exhaustively-documented "
        "public knowledge independent of this project. No generic "
        "source-language description was added to A (§7's remedy is "
        "unnecessary here)."
    ),
    "evidence_against_harmful_leakage": (
        "If the models had memorized the corpus's expected verdicts, "
        "condition A would approach 100%. It does not (5-seed pooled A "
        "accuracy: Haiku 91%, Gemini 82%), and its errors concentrate on "
        "exactly the C-UB-but-RV64-defined wedges, where the models reason "
        "confidently from the C standard to the WRONG answer. That failure "
        "signature is reasoning from general C knowledge, not reciting this "
        "benchmark's answer key; per-seed variance (non-deterministic "
        "verdicts on the same cell) further argues against rote recall."
    ),
    "checked_at": now,
}

note = (
    "v0.6 two-family A/B/C, BENCHMARKING.md §7-grade (>=2 unrelated families, "
    ">=5 seeds). Determinism: 104/104 corpus tasks recompiled byte-identical "
    "(check_determinism.py over full corpus). See runs/v0.6-two-family/RESULTS.md."
)

manifests = [
    "runs/v0.6-two-family/slot_A/manifest.json",
    "runs/v0.6-two-family/slot_CC_haiku/manifest.json",
    "runs/v0.6-two-family/t4_addendum/slot_A/manifest.json",
    "runs/v0.6-two-family/t4_addendum/slot_CC_haiku/manifest.json",
]
for mp in manifests:
    p = Path(mp)
    if not p.exists():
        print("MISSING", mp); continue
    m = json.loads(p.read_text())
    m["determinism_check"] = det
    m["leakage_check"] = leakage
    n = note
    if "t4_addendum" in mp:
        n = ("v0.6 T4 addendum (5 T4 tasks x A/B/C x 5 seeds x 2 families) for "
             "the §9.7 lift-quality rubric. " + note.split('. ',1)[1])
    m["notes"] = n
    p.write_text(json.dumps(m, indent=2) + "\n")
    print("updated", mp, "| det", det["pass_count"], "/", det["sample_size"])
