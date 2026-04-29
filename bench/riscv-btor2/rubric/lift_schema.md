# T4 lift schema

`witness_schema.md` covers verdict + witness fingerprint (the
deterministic part of the rubric). This file extends it for **T4**
tasks, which additionally grade the LLM's source-level
*explanation* of the verdict via the optional `lift` field.

T1/T2/T3 tasks emit `lift: null` and never invoke this schema.

## Two halves of the contract

### Author side: `task.toml [lift]`

Required for every T4 task. Captures what a perfect-score answer
would identify as the source-level cause of the verdict.

```toml
[lift]
# REQUIRED. The PC of the instruction at which the
# refutation/proof "lands" — typically the divergence point or
# the instruction whose schema-level semantics the LLM must
# articulate.
expected_cause_pc = 0x10004

# REQUIRED. The mnemonic at expected_cause_pc; redundant given the
# objdump but useful so the rubric LLM doesn't have to re-derive it.
expected_cause_mnemonic = "ADDIW"

# OPTIONAL. Other PCs whose identification the rubric should also
# accept as correct — e.g., a sequence of two instructions where
# either is a defensible "cause".
acceptable_alternative_pcs = [0x10000]

# REQUIRED. Two or three sentences naming the source-level
# mechanism, in the same prose register the LLM is being asked to
# produce. Used as the reference for the score-2 anchor; the rubric
# LLM scores partial credit on closeness to this.
expected_explanation_summary = """
ADDIW computes the 32-bit add and sign-extends the result to 64
bits. With the high bit of the low-32 result set, the value
written to x{rd} is the sign-extended form 0xFFFFFFFF80000000,
not the bare 0x80000000 a naive 32-bit reading would predict.
"""

# OPTIONAL. Source-level vocabulary the explanation should
# touch. The rubric LLM uses this as a soft signal — presence of
# any keyword from this list is positive but not required.
expected_keywords = ["sign-extend", "low 32", "ADDIW", "high bit"]
```

### LLM side: `lift` in the answer JSON

When the task is T4, the LLM's emitted final answer JSON includes
a non-null `lift` object:

```json
{
  "verdict":   "unreachable",
  "confidence": 0.91,
  "reason":    "...",
  "witness":   null,
  "lift": {
    "cause_pc":       65540,
    "cause_mnemonic": "ADDIW",
    "explanation":    "ADDIW takes the low 32 bits of the sum and sign-extends to 64; with bit 31 set, x10 ends up at 0xFFFFFFFF80000000 instead of 0x80000000."
  }
}
```

- `cause_pc` (integer) — the PC the LLM thinks is the lift target.
- `cause_mnemonic` (string) — the LLM's read of the mnemonic at that PC.
- `explanation` (string, 1–3 sentences) — the source-level mechanism.

The rubric LLM scores this against the author-side `[lift]` table.

## Score rubric (0/1/2)

The scoring is the same for the rubric LLM and for the manual
grader (see `manual_grading.md`).

| Score | Meaning |
|---:|---|
| **2** | `cause_pc` matches `expected_cause_pc` (or one of `acceptable_alternative_pcs`), AND `explanation` captures the source-level mechanism (substantively overlaps with `expected_explanation_summary`; at least one `expected_keywords` term or its synonym present). |
| **1** | One of the two halves is right and the other is partially right. E.g., `cause_pc` matches but the explanation misses the key insight (says "the assembler did something tricky" instead of naming the mechanism); or the explanation is on point but `cause_pc` points at an instruction one step off — still in the same lowering family. |
| **0** | Neither half is right, OR the explanation contradicts schema-level semantics (e.g., asserts an instruction has effects it doesn't have), OR the LLM emits `lift: null` for a T4 task. |

The matcher's deterministic `verdict` and `witness_match` columns
are reported separately. A T4 task can have a wrong verdict and
still be scored on lift; the table just records both.

## What the rubric does NOT score

- **Eloquence or length.** A terse correct explanation scores the
  same as a verbose one.
- **Disagreement with the author's wording.** The author's
  `expected_explanation_summary` is one defensible phrasing, not
  the only one. The rubric LLM is told this explicitly.
- **Use of ABI aliases vs numeric register names.** Both are accepted.
- **Witness fingerprint correctness.** That's `matcher.py`'s job.
- **Tool-use efficiency under condition B.** Cost-to-answer is a
  separate metric (`§5`); the rubric scores correctness only.
