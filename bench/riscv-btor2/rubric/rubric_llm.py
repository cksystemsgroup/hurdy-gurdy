"""Rubric LLM grading for the T4 lift field (BENCHMARKING.md §9.7).

Verdict and witness are graded deterministically by ``matcher.py``; the
**lift quality** column is judged by an LLM on a 0/1/2 scale per the
prompt in ``rubric_prompt.md``. This module is the thin glue that turns
a (task, observed, transcript) tuple into a rubric-LLM call and parses
the structured response.

Usable as a library:

    from rubric_llm import grade_lift
    out = grade_lift(task_dir, observed, transcript_text,
                     model_config=harness.MODELS["rubric"])
    # {"score": 0|1|2, "matched_pc": bool, "matched_explanation": bool,
    #  "reason": str, "redactions": int, "model_id": str}

The harness calls this from ``grade()`` for T4 tasks (and only T4 tasks).
T1/T2/T3 grading does not invoke the rubric.

Network and auth: the rubric LLM is the OpenAI adapter routed at
``models.github.ai`` with a ``models:read``-scoped GitHub PAT in
``GITHUB_TOKEN`` (see ``llms.md`` "Rubric LLM" slot). When the token is
not set, ``grade_lift`` returns ``{"score": None, "reason": "rubric_llm:
GITHUB_TOKEN unset"}`` and the harness records ``lift_score = None`` —
no fallback grader is silently substituted.

Blindness: per §9.7, the rubric runs **blind to condition and to the
model under test**. Before invocation the transcript is passed through
``redact_transcript()`` which scrubs model-family tokens, condition
labels, and slot ids. The redaction count is reported back so a reviewer
can audit.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any


_RUBRIC_DIR = Path(__file__).resolve().parent
_BENCH_ROOT = _RUBRIC_DIR.parent


# === Redactions (rubric_prompt.md "Redactions before invocation") ==========


# Model-family tokens. Match the literal vendor-prefix forms enumerated
# in rubric_prompt.md plus version/snapshot suffixes.
_MODEL_RE = re.compile(
    r"\b("
    r"claude-[\w.\-]+"          # claude-opus-4-7, claude-haiku-4-5-20251001
    r"|gpt-[\w.\-]+"            # gpt-4.1-mini, gpt-5
    r"|gemini-[\w.\-]+"         # gemini-2.5-flash
    r"|llama-[\w.\-]+"          # llama-3.1-...
    r"|openai/[\w.\-]+"         # openai/gpt-4.1-mini (GitHub Models prefix)
    r"|anthropic/[\w.\-]+"
    r"|google/[\w.\-]+"
    r")\b",
    re.IGNORECASE,
)
_SLOT_RE = re.compile(r"\bslot_(?:A|B|C|CC|CC_haiku|D|test)\b", re.IGNORECASE)
# "condition A" / "condition: B" / "Condition C". Standalone single-letter
# A/B/C/D would over-match; we anchor on the word "condition".
_CONDITION_RE = re.compile(
    r"\b(condition)([\s:=]+)([ABCD])\b",
    re.IGNORECASE,
)


def redact_transcript(text: str) -> tuple[str, int]:
    """Scrub vendor / condition / slot identifiers from ``text``.

    Returns ``(redacted_text, redaction_count)``. The count includes one
    per replaced token; reviewers can compare it against the run
    manifest to audit blindness.
    """
    count = 0

    def _model_sub(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "<MODEL>"

    def _slot_sub(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "<SLOT>"

    def _cond_sub(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{m.group(1)}{m.group(2)}<CONDITION>"

    out = _MODEL_RE.sub(_model_sub, text)
    out = _SLOT_RE.sub(_slot_sub, out)
    out = _CONDITION_RE.sub(_cond_sub, out)
    return out, count


# === Prompt assembly =======================================================


_SYSTEM_PROMPT = """\
You are a rubric grader. You score one piece of a transcript: the
LLM's source-level *explanation* of why the verdict on a small
RV64IMC analysis question is what it is. Your job is to assign a
0/1/2 score and a one-sentence rationale.

You do NOT see which model produced the transcript, which
condition the run was in, or any solver verdicts beyond what is in
the transcript itself. Do not speculate about these. Score only
what the transcript contains.

You will be given:
- TASK: the question text, the source program, and the expected
  source-level cause of the verdict (the perfect-score reference).
- OBSERVED: the LLM's emitted `lift` field (cause_pc,
  cause_mnemonic, explanation).
- TRANSCRIPT: the LLM's prior reasoning, included for context.
  You may consult it but the score is on `OBSERVED.lift`.

Score (0/1/2) per `bench/riscv-btor2/rubric/lift_schema.md`:

  2  cause_pc matches expected (or any acceptable_alternative_pcs)
     AND the explanation captures the source-level mechanism.
  1  one half is right, the other partially right. Examples:
     - PC matches but explanation hand-waves ("the compiler did
       something tricky") instead of naming the mechanism.
     - Explanation names the mechanism correctly but cause_pc is
       off by one instruction within the same lowering family.
  0  neither half is right, or the explanation contradicts the
     schema (asserts wrong semantics), or `OBSERVED.lift` is null.

Output STRICTLY this JSON object — nothing before, nothing after:

{
  "score":   0 | 1 | 2,
  "reason":  "<one sentence, ≤ 30 words>",
  "matched_pc":  true | false,
  "matched_explanation": true | false
}

Be strict. The rubric is calibrated on the assumption that 1 is
genuinely partial — give 1 only when you can name BOTH the right
half and the missing-or-partial half.
"""


def _format_pc_list(values: list[int] | None) -> str:
    if not values:
        return "(none)"
    return ", ".join(f"0x{int(v):x}" for v in values)


def _read_task(task_dir: Path) -> dict[str, Any]:
    with (task_dir / "task.toml").open("rb") as f:
        return tomllib.load(f)


def _read_source_s(task_dir: Path) -> str:
    src = task_dir / "source.S"
    return src.read_text() if src.exists() else "(source.S not present)"


def build_user_prompt(
    task_dir: Path,
    observed: dict[str, Any],
    transcript_text: str,
) -> tuple[str, int]:
    """Construct the per-task user prompt. Returns (prompt, redactions)."""
    task = _read_task(task_dir)
    lift = task.get("lift") or {}
    observed_lift = observed.get("lift")

    redacted_transcript, redactions = redact_transcript(transcript_text or "")

    expected_pc = int(lift.get("expected_cause_pc", 0))
    alt_pcs = list(lift.get("acceptable_alternative_pcs") or [])

    prompt = (
        "TASK\n"
        "====\n\n"
        f"Task id: {task['task']['id']}\n"
        "Difficulty: T4\n"
        f"Lowering-sensitive: {task['task'].get('lowering_sensitive', False)}\n\n"
        "Question:\n\n"
        f"{task.get('question', {}).get('text', '').strip()}\n\n"
        "Source (`source.S`):\n\n"
        "```asm\n"
        f"{_read_source_s(task_dir).rstrip()}\n"
        "```\n\n"
        f"Expected verdict: {task['expected']['verdict']}\n\n"
        "Expected lift (the perfect-score reference; the OBSERVED need not\n"
        "match this verbatim, only substantively):\n\n"
        f"  expected_cause_pc:        0x{expected_pc:x}\n"
        f"  expected_cause_mnemonic:  {lift.get('expected_cause_mnemonic', '')}\n"
        f"  acceptable_alternative_pcs: {_format_pc_list(alt_pcs)}\n"
        "  expected_explanation_summary:\n\n"
        f"{(lift.get('expected_explanation_summary') or '').rstrip()}\n\n"
        f"  expected_keywords (soft signal): "
        f"{lift.get('expected_keywords') or []}\n\n\n"
        "OBSERVED\n"
        "========\n\n"
        "The LLM under test emitted this `lift` field as part of its final\n"
        "answer JSON:\n\n"
        f"{json.dumps(observed_lift, indent=2)}\n\n\n"
        "TRANSCRIPT (context)\n"
        "====================\n\n"
        f"{redacted_transcript.rstrip()}\n\n\n"
        "Score the OBSERVED lift per the rubric. Output strictly the JSON\n"
        "shape from the system prompt — no preamble, no postscript, no\n"
        "markdown fence.\n"
    )
    return prompt, redactions


# === Response parsing ======================================================


def _parse_rubric_json(text: str) -> dict[str, Any] | None:
    """Extract the rubric JSON object from a model response.

    The system prompt asks for "STRICTLY this JSON object", but real
    models occasionally wrap it in a fence or prefix it with a sentence.
    Be lenient: try a direct parse, then fall back to the last
    balanced ``{...}`` block in the text.
    """
    if not text:
        return None
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Find the last balanced top-level object.
    depth = 0
    start = -1
    candidates: list[tuple[int, int]] = []
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append((start, i + 1))
                start = -1
    for s, e in reversed(candidates):
        try:
            return json.loads(text[s:e])
        except json.JSONDecodeError:
            continue
    return None


def _coerce_report(parsed: dict[str, Any]) -> dict[str, Any]:
    score = parsed.get("score")
    if score not in (0, 1, 2):
        # Out-of-vocabulary score: treat as failure to grade. A T4 row
        # with an unparseable rubric output should surface as null in
        # the manifest, not a guessed value.
        score = None
    return {
        "score":               score,
        "matched_pc":          bool(parsed.get("matched_pc")),
        "matched_explanation": bool(parsed.get("matched_explanation")),
        "reason":              str(parsed.get("reason", "")).strip()[:300],
    }


# === Public API ============================================================


_NO_TOKEN_REASON = "rubric_llm: GITHUB_TOKEN unset"
_NO_LIFT_REASON = "rubric_llm: observed.lift is null (T4 tasks must emit a lift)"


def grade_lift(
    task_dir: Path,
    observed: dict[str, Any],
    transcript_text: str,
    *,
    model_config: dict[str, Any],
    call_llm=None,
) -> dict[str, Any]:
    """Grade the T4 lift field. Returns a dict suitable for the manifest's
    ``runs[].graded.lift_score`` slot.

    Shape::

        {
          "score": 0 | 1 | 2 | None,
          "matched_pc": bool,
          "matched_explanation": bool,
          "reason": str,
          "redactions": int,
          "model_id": str,
        }

    Score is ``None`` when the rubric LLM cannot be reached (no API key,
    or response is unparseable) or when the observed lift is itself
    null. The harness must record ``score`` verbatim — including
    ``None`` — and not silently substitute a default.

    ``call_llm`` defaults to ``harness.call_llm``; the parameter is
    primarily for tests that want to inject a stub response without
    spinning up the OpenAI client.
    """
    # No-API-key path: refuse to silently grade with a stub.
    api_key_env = model_config["params"].get("api_key_env")
    if call_llm is None and api_key_env and not os.environ.get(api_key_env):
        return {
            "score":               None,
            "matched_pc":          False,
            "matched_explanation": False,
            "reason":              _NO_TOKEN_REASON,
            "redactions":          0,
            "model_id":            model_config["model_id"],
        }

    # Null-lift short-circuit: per the rubric, a T4 task that emits
    # ``lift: null`` is automatically score 0. No need to spend a
    # rubric-LLM call.
    if observed.get("lift") is None:
        return {
            "score":               0,
            "matched_pc":          False,
            "matched_explanation": False,
            "reason":              _NO_LIFT_REASON,
            "redactions":          0,
            "model_id":            model_config["model_id"],
        }

    user_prompt, redactions = build_user_prompt(
        task_dir, observed, transcript_text or ""
    )

    if call_llm is None:
        # Late import: avoid pulling harness.py into the module graph
        # at import time so tests can stub call_llm without a vendor
        # SDK installed.
        sys.path.insert(0, str(_BENCH_ROOT))
        import harness  # type: ignore
        call_llm = harness.call_llm

    # Compose the single user-turn prompt: the system prompt + the
    # filled-in user prompt. The OpenAI adapter takes a single
    # ``system_or_user_text`` and prepends it as a user message, so we
    # pre-concatenate the two pieces with a separator the model can
    # parse.
    full_text = (
        "[SYSTEM]\n" + _SYSTEM_PROMPT + "\n\n[TASK]\n" + user_prompt
    )

    resp = call_llm(
        family=model_config["family"],
        model_id=model_config["model_id"],
        system_or_user_text=full_text,
        tools=None,
        params=model_config["params"],
        seed=0,
        on_tool_call=lambda name, payload: {
            "error": f"rubric LLM does not allow tool calls (got {name!r})"
        },
    )

    parsed = _parse_rubric_json(resp.text or "")
    if parsed is None:
        return {
            "score":               None,
            "matched_pc":          False,
            "matched_explanation": False,
            "reason":              "rubric_llm: response not JSON-parseable",
            "redactions":          redactions,
            "model_id":            model_config["model_id"],
        }

    out = _coerce_report(parsed)
    out["redactions"] = redactions
    out["model_id"] = model_config["model_id"]
    return out
