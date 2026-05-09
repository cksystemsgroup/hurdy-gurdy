"""Tests for bench/riscv-btor2/rubric/rubric_llm.py.

Two layers:

1. **Pure unit tests** (always run): exercise prompt assembly,
   redactions, JSON parsing, and the wiring of ``grade_lift`` against
   a stub ``call_llm`` injected via the ``call_llm=`` parameter. No
   network and no API key required.

2. **Live integration test** (opt-in): grades a hand-written
   reference lift for ``0003-addiw-sign-ext`` against the real rubric
   LLM (OpenAI via GitHub Models). Skipped unless ``GITHUB_TOKEN`` is
   present AND ``RISCV_BTOR2_RUBRIC_LIVE=1``. The opt-in flag prevents
   accidental token consumption during routine ``pytest`` runs.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
BENCH = REPO / "bench" / "riscv-btor2"
RUBRIC_DIR = BENCH / "rubric"
CORPUS = BENCH / "corpus"


# Make the bench module path importable. ``rubric_llm`` lives in
# ``rubric/`` (sibling to ``matcher.py``); the import path mirrors the
# one ``harness.grade()`` uses at runtime.
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(RUBRIC_DIR))


@pytest.fixture
def task_dir() -> Path:
    d = CORPUS / "0003-addiw-sign-ext"
    if not (d / "task.toml").exists():
        pytest.skip("0003-addiw-sign-ext corpus task missing")
    return d


# === Pure unit tests =======================================================


def test_redact_transcript_strips_model_slot_and_condition():
    import rubric_llm  # type: ignore
    text = (
        "Run with claude-haiku-4-5-20251001 in slot_CC_haiku under "
        "condition B. Compare with gpt-4.1-mini in slot_test on Condition: A."
    )
    out, n = rubric_llm.redact_transcript(text)
    assert "<MODEL>" in out
    assert "<SLOT>" in out
    assert "<CONDITION>" in out
    assert "claude-" not in out
    assert "gpt-" not in out
    assert "slot_CC_haiku" not in out
    assert "slot_test" not in out
    # 2 model tokens + 2 slot tokens + 2 condition tokens = 6
    assert n == 6


def test_redact_transcript_leaves_neutral_text_alone():
    import rubric_llm  # type: ignore
    text = "ADDIW computes the 32-bit add and sign-extends to 64."
    out, n = rubric_llm.redact_transcript(text)
    assert out == text
    assert n == 0


def test_parse_rubric_json_strict_object():
    import rubric_llm  # type: ignore
    raw = '{"score": 2, "reason": "ok", "matched_pc": true, "matched_explanation": true}'
    parsed = rubric_llm._parse_rubric_json(raw)
    assert parsed is not None
    assert parsed["score"] == 2


def test_parse_rubric_json_in_markdown_fence():
    import rubric_llm  # type: ignore
    raw = (
        "Sure, here's my rating:\n\n"
        "```json\n"
        '{"score": 1, "reason": "PC right, prose vague",\n'
        ' "matched_pc": true, "matched_explanation": false}\n'
        "```\n"
    )
    parsed = rubric_llm._parse_rubric_json(raw)
    assert parsed is not None
    assert parsed["score"] == 1
    assert parsed["matched_pc"] is True


def test_parse_rubric_json_picks_last_block_when_multiple():
    import rubric_llm  # type: ignore
    raw = (
        "First I considered {bogus: not json} then settled on:\n"
        '{"score": 0, "reason": "lift was null", '
        '"matched_pc": false, "matched_explanation": false}'
    )
    parsed = rubric_llm._parse_rubric_json(raw)
    assert parsed is not None
    assert parsed["score"] == 0


def test_build_user_prompt_includes_expected_lift(task_dir: Path):
    import rubric_llm  # type: ignore
    observed = {
        "verdict": "unreachable",
        "lift": {
            "cause_pc": 65540,
            "cause_mnemonic": "ADDIW",
            "explanation": "ADDIW sign-extends to 64.",
        },
    }
    prompt, redactions = rubric_llm.build_user_prompt(
        task_dir, observed, transcript_text="(no transcript)"
    )
    # Expected lift fields must appear in the user prompt verbatim or
    # in their canonical hex form. Otherwise the grader has no
    # reference to compare against.
    assert "0x10004" in prompt or "65540" in prompt  # expected_cause_pc
    assert "ADDIW" in prompt
    assert "sign-extend" in prompt or "sign extension" in prompt
    # Observed must be there too.
    assert "65540" in prompt
    assert "ADDIW sign-extends" in prompt
    # Nothing to redact in this transcript.
    assert redactions == 0


def test_grade_lift_returns_score_zero_for_null_lift(task_dir: Path):
    import rubric_llm  # type: ignore
    observed = {"verdict": "unreachable", "lift": None}
    out = rubric_llm.grade_lift(
        task_dir,
        observed,
        transcript_text="",
        model_config={"family": "openai", "model_id": "stub",
                      "params": {"api_key_env": "NEVER_SET_ENV_VAR_XYZ"}},
        # Provide a sentinel call_llm so the missing-token path doesn't
        # short-circuit; we want to verify the null-lift branch.
        call_llm=lambda **_: pytest.fail("rubric LLM should not be called for null lift"),
    )
    assert out["score"] == 0
    assert "null" in out["reason"]
    assert out["matched_pc"] is False


def test_grade_lift_short_circuits_when_token_missing(task_dir: Path, monkeypatch):
    import rubric_llm  # type: ignore
    monkeypatch.delenv("ABSENT_FOR_THIS_TEST", raising=False)
    observed = {
        "verdict": "unreachable",
        "lift": {
            "cause_pc": 65540, "cause_mnemonic": "ADDIW",
            "explanation": "sign extends low 32",
        },
    }
    out = rubric_llm.grade_lift(
        task_dir,
        observed,
        transcript_text="(any)",
        model_config={
            "family":  "openai",
            "model_id": "openai/gpt-4.1-mini",
            "params":  {"api_key_env": "ABSENT_FOR_THIS_TEST"},
        },
        call_llm=None,  # default path uses harness.call_llm
    )
    assert out["score"] is None
    assert "GITHUB_TOKEN unset" in out["reason"] or "ABSENT_FOR_THIS_TEST" in out["reason"] \
        or "unset" in out["reason"]


@dataclass
class _StubResponse:
    text: str


def test_grade_lift_passes_through_stubbed_call_llm(task_dir: Path):
    import rubric_llm  # type: ignore
    observed = {
        "verdict": "unreachable",
        "lift": {
            "cause_pc": 65540, "cause_mnemonic": "ADDIW",
            "explanation": "ADDIW: 32-bit add, then sign-extend to 64. With bit 31 set, x10 = 0xFFFFFFFF80000000.",
        },
    }
    captured = {}

    def stub_call_llm(**kw):
        captured.update(kw)
        return _StubResponse(text=json.dumps({
            "score": 2, "reason": "PC and mechanism both right.",
            "matched_pc": True, "matched_explanation": True,
        }))

    out = rubric_llm.grade_lift(
        task_dir,
        observed,
        transcript_text="(transcript)",
        model_config={"family": "openai", "model_id": "stub-id",
                      "params": {"temperature": 0.0}},
        call_llm=stub_call_llm,
    )
    assert out["score"] == 2
    assert out["matched_pc"] is True
    assert out["matched_explanation"] is True
    assert out["model_id"] == "stub-id"
    # The stub should have received the rubric system + user prompt
    # combined into one user-turn payload.
    assert "[SYSTEM]" in captured["system_or_user_text"]
    assert "[TASK]" in captured["system_or_user_text"]
    # Tools must be off for the rubric.
    assert captured["tools"] is None


def test_grade_lift_score_one_for_partial_lift(task_dir: Path):
    """The rubric LLM, not us, decides 0/1/2 — but we must round-trip
    a partial-credit response correctly through the parser."""
    import rubric_llm  # type: ignore
    observed = {
        "verdict": "unreachable",
        "lift": {
            "cause_pc": 65540, "cause_mnemonic": "ADDIW",
            "explanation": "Some 32-bit thing happens.",
        },
    }

    def stub_call_llm(**_):
        return _StubResponse(text=(
            "Here is my analysis. The PC is right but the explanation hand-waves.\n\n"
            "```json\n"
            '{"score": 1, "reason": "PC right, prose vague",\n'
            ' "matched_pc": true, "matched_explanation": false}\n'
            "```"
        ))

    out = rubric_llm.grade_lift(
        task_dir, observed, transcript_text="",
        model_config={"family": "openai", "model_id": "stub",
                      "params": {}},
        call_llm=stub_call_llm,
    )
    assert out["score"] == 1
    assert out["matched_pc"] is True
    assert out["matched_explanation"] is False


def test_grade_lift_returns_none_on_unparseable(task_dir: Path):
    import rubric_llm  # type: ignore
    observed = {
        "verdict": "unreachable",
        "lift": {
            "cause_pc": 65540, "cause_mnemonic": "ADDIW",
            "explanation": "anything",
        },
    }
    out = rubric_llm.grade_lift(
        task_dir, observed, transcript_text="",
        model_config={"family": "openai", "model_id": "stub",
                      "params": {}},
        call_llm=lambda **_: _StubResponse(
            text="The rubric LLM crashed and returned this prose."),
    )
    assert out["score"] is None
    assert "JSON-parseable" in out["reason"] or "not" in out["reason"]


def test_grade_lift_records_redactions(task_dir: Path):
    import rubric_llm  # type: ignore
    observed = {
        "verdict": "unreachable",
        "lift": {
            "cause_pc": 65540, "cause_mnemonic": "ADDIW",
            "explanation": "anything",
        },
    }
    out = rubric_llm.grade_lift(
        task_dir, observed,
        transcript_text="claude-opus-4-7 ran in slot_CC under condition B.",
        model_config={"family": "openai", "model_id": "stub",
                      "params": {}},
        call_llm=lambda **_: _StubResponse(text='{"score":2,"reason":"x","matched_pc":true,"matched_explanation":true}'),
    )
    # 1 model + 1 slot + 1 condition.
    assert out["redactions"] == 3


# === harness.grade() integration ==========================================


def test_harness_grade_t4_records_lift_score_when_rubric_configured(task_dir: Path):
    """T4 + rubric_config + stub call -> grade() populates lift_score."""
    import harness  # type: ignore
    task = next(t for t in harness.discover_tasks() if t.id == "0003-addiw-sign-ext")

    observed = {
        "verdict": "unreachable", "confidence": 0.9, "reason": "...",
        "witness": None,
        "lift": {
            "cause_pc": 65540, "cause_mnemonic": "ADDIW",
            "explanation": "ADDIW sign-extends low 32 to 64.",
        },
    }

    def stub(**_):
        return _StubResponse(text='{"score":2,"reason":"ok","matched_pc":true,"matched_explanation":true}')

    out = harness.grade(
        task, observed,
        transcript_text="(stubbed)",
        rubric_config={"family": "openai", "model_id": "stub",
                       "params": {}},
        rubric_call_llm=stub,
    )
    assert out["lift_score"] == 2
    assert out["lift_matched_pc"] is True
    assert out["lift_grader_model"] == "stub"


def test_harness_grade_t4_no_rubric_records_none(task_dir: Path):
    """T4 without rubric_config -> lift_score is None with reason."""
    import harness  # type: ignore
    task = next(t for t in harness.discover_tasks() if t.id == "0003-addiw-sign-ext")
    observed = {"verdict": "unreachable", "confidence": 0.9,
                "reason": "...", "witness": None,
                "lift": {"cause_pc": 65540, "cause_mnemonic": "ADDIW",
                         "explanation": "x"}}
    out = harness.grade(task, observed)
    assert out["lift_score"] is None
    assert "not configured" in out["lift_reason"]


def test_harness_grade_t1_does_not_invoke_rubric():
    """T1 / T2 / T3 tasks do not get a lift_score, even if rubric_config
    is supplied."""
    import harness  # type: ignore
    # Pick any non-T4 task.
    task = next(t for t in harness.discover_tasks() if t.difficulty != "T4")
    observed = {"verdict": task.expected_verdict, "confidence": 0.9,
                "reason": "...", "witness": None, "lift": None}
    out = harness.grade(
        task, observed,
        transcript_text="anything",
        rubric_config={"family": "openai", "model_id": "stub", "params": {}},
        rubric_call_llm=lambda **_: pytest.fail(
            "rubric LLM must not be called for non-T4 tasks"),
    )
    assert "lift_score" not in out


# === Live integration (opt-in) ============================================


@pytest.mark.skipif(
    not (os.environ.get("GITHUB_TOKEN") and os.environ.get("RISCV_BTOR2_RUBRIC_LIVE") == "1"),
    reason="set GITHUB_TOKEN and RISCV_BTOR2_RUBRIC_LIVE=1 to run live rubric test",
)
def test_grade_lift_live_perfect_reference_scores_two(task_dir: Path):
    import rubric_llm  # type: ignore
    import harness  # type: ignore

    # The task's own [lift].expected_explanation_summary is the
    # perfect-score reference. If we feed it back as the OBSERVED
    # explanation, the rubric LLM should score 2.
    import tomllib
    with (task_dir / "task.toml").open("rb") as f:
        task_toml = tomllib.load(f)
    expected = task_toml["lift"]
    observed = {
        "verdict": "unreachable",
        "lift": {
            "cause_pc":       expected["expected_cause_pc"],
            "cause_mnemonic": expected["expected_cause_mnemonic"],
            "explanation":    expected["expected_explanation_summary"].strip(),
        },
    }

    out = rubric_llm.grade_lift(
        task_dir, observed,
        transcript_text="(no transcript)",
        model_config=harness.MODELS["rubric"],
    )
    assert out["score"] == 2, out
    assert out["matched_pc"] is True
    assert out["matched_explanation"] is True
