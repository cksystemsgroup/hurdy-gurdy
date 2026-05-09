"""Tests for B2: multi-question task format.

Three layers:

1. **Schema parsing** — Task.questions returns the right list shape for
   single- and multi-question tasks; ``_parse_questions`` rejects
   malformed inputs.

2. **Matcher** — ``match(task_dir, observed, question_id=...)`` reads
   ``[questions.qN]``; ``match_all`` returns one report per question.
   Single-question tasks remain backward-compatible.

3. **Harness orchestration** — ``run_one_task`` loops through questions
   in dry-run mode, threading prior-observation context into the prompt
   and injecting LearnedFacts into the spec for downstream questions.
   No LLM calls.

The multi-question fixture lives in ``_multi_q_fixture/`` next to this
file; it deliberately has no built ELF so the tests stay hermetic.
"""

from __future__ import annotations

import json
import shutil
import sys
import tomllib
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
BENCH = REPO / "bench" / "riscv-btor2"
RUBRIC_DIR = BENCH / "rubric"
FIXTURE = Path(__file__).parent / "_multi_q_fixture"

sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(RUBRIC_DIR))


@pytest.fixture
def fixture_dir(tmp_path: Path) -> Path:
    """Copy the multi-question fixture to a tmp dir.

    Each test gets its own copy so tests can mutate ``task.toml`` (or
    swap in malformed variants) without bleeding across runs.
    """
    dst = tmp_path / "_multi_q_fixture"
    shutil.copytree(FIXTURE, dst)
    return dst


# === Schema parsing =======================================================


def test_legacy_single_question_tasks_remain_unchanged():
    import harness  # type: ignore
    tasks = harness.discover_tasks()
    assert tasks
    for t in tasks:
        # Every existing corpus task is single-question. id=None is the
        # backward-compat sentinel.
        assert len(t.questions) == 1, f"{t.id} unexpectedly multi-question"
        assert t.questions[0].id is None
        assert t.questions[0].text == t.raw["question"]["text"]
        assert t.questions[0].expected_verdict == t.raw["expected"]["verdict"]
        assert t.is_multi_question is False


def test_multi_question_fixture_parses_two_questions(fixture_dir: Path):
    import harness  # type: ignore
    tasks = harness.discover_tasks(corpus=fixture_dir.parent)
    fixture = next(t for t in tasks if t.id == "fixture-multi-q")
    assert fixture.is_multi_question
    assert [q.id for q in fixture.questions] == ["q1", "q2"]
    assert fixture.questions[0].expected_verdict == "proved"
    assert fixture.questions[1].inherits_learned_from == ["q1"]
    # Each question's spec is the right per-question file.
    assert "gtu(reg(18)" in fixture.questions[0].spec["fields"]["property"]["expression"]
    assert "geu(reg(10)" in fixture.questions[1].spec["fields"]["property"]["expression"]


def test_parse_questions_rejects_both_legacy_and_multi(tmp_path: Path):
    import harness  # type: ignore
    bad = tmp_path / "bad-task"
    bad.mkdir()
    (bad / "task.toml").write_text("""
[task]
id = "bad"
task_class = "x"
difficulty = "T1"
oracle_provenance = "test"

[question]
text = "old shape"

[expected]
verdict = "unknown"

[questions.q1]
text = "new shape"
expected_verdict = "unknown"
""")
    (bad / "spec.json").write_text(json.dumps({"pair": "riscv-btor2", "fields": {}}))
    with (bad / "task.toml").open("rb") as f:
        raw = tomllib.load(f)
    with pytest.raises(ValueError, match="both"):
        harness._parse_questions(bad, raw)


def test_parse_questions_rejects_non_contiguous_ids(tmp_path: Path):
    import harness  # type: ignore
    bad = tmp_path / "skip-task"
    bad.mkdir()
    (bad / "task.toml").write_text("""
[task]
id = "skip"
task_class = "x"
difficulty = "T1"
oracle_provenance = "test"

[questions.q1]
text = "first"
expected_verdict = "unknown"

[questions.q3]
text = "third (q2 missing)"
expected_verdict = "unknown"
""")
    (bad / "spec.json").write_text(json.dumps({"pair": "riscv-btor2", "fields": {}}))
    with (bad / "task.toml").open("rb") as f:
        raw = tomllib.load(f)
    with pytest.raises(ValueError, match="contiguous"):
        harness._parse_questions(bad, raw)


def test_parse_questions_rejects_inherits_from_unknown_q(tmp_path: Path):
    import harness  # type: ignore
    bad = tmp_path / "bad-inherit"
    bad.mkdir()
    (bad / "task.toml").write_text("""
[task]
id = "bad-inherit"
task_class = "x"
difficulty = "T3"
oracle_provenance = "test"

[questions.q1]
text = "first"
expected_verdict = "proved"
inherits_learned_from = ["q0"]
""")
    (bad / "spec.json").write_text(json.dumps({"pair": "riscv-btor2", "fields": {}}))
    with (bad / "task.toml").open("rb") as f:
        raw = tomllib.load(f)
    with pytest.raises(ValueError, match="not a prior question"):
        harness._parse_questions(bad, raw)


# === Matcher (multi-question) ============================================


def test_matcher_single_question_unchanged():
    import matcher  # type: ignore
    real = BENCH / "corpus" / "0001-x0-write-dropped"
    if not real.exists():
        pytest.skip("0001-x0-write-dropped corpus task missing")
    report = matcher.match(real, {"verdict": "unreachable"})
    assert report.verdict_correct is True
    assert report.expected_verdict == "unreachable"


def test_matcher_match_with_question_id_reads_questions_block(fixture_dir: Path):
    import matcher  # type: ignore
    fx = fixture_dir
    # q1 expects "proved"; observed "proved" must PASS.
    r = matcher.match(fx, {"verdict": "proved"}, question_id="q1")
    assert r.verdict_correct is True
    # q2 expects "proved"; observed "unknown" must FAIL.
    r2 = matcher.match(fx, {"verdict": "unknown"}, question_id="q2")
    assert r2.verdict_correct is False
    assert "verdict mismatch" in " ".join(r2.failures)


def test_matcher_match_with_unknown_question_id_raises(fixture_dir: Path):
    import matcher  # type: ignore
    fx = fixture_dir
    with pytest.raises(KeyError, match="q99"):
        matcher.match(fx, {"verdict": "proved"}, question_id="q99")


def test_matcher_match_all_returns_one_report_per_question(fixture_dir: Path):
    import matcher  # type: ignore
    fx = fixture_dir
    reports = matcher.match_all(fx, [
        {"verdict": "proved"},
        {"verdict": "proved"},
    ])
    assert len(reports) == 2
    assert all(r.verdict_correct for r in reports)
    # Synthetic task ids carry the #qN suffix so manifest aggregation
    # can group reports per question.
    assert reports[0].task_id.endswith("#q1")
    assert reports[1].task_id.endswith("#q2")


def test_matcher_match_all_validates_observation_count(fixture_dir: Path):
    import matcher  # type: ignore
    fx = fixture_dir
    with pytest.raises(ValueError, match=r"2 questions"):
        matcher.match_all(fx, [{"verdict": "proved"}])


def test_matcher_validate_task_accepts_multi_q(fixture_dir: Path):
    import matcher  # type: ignore
    fx = fixture_dir
    problems = matcher.validate_task(fx)
    assert problems == []


def test_matcher_validate_task_flags_double_shape(tmp_path: Path):
    import matcher  # type: ignore
    bad = tmp_path / "double"
    bad.mkdir()
    (bad / "task.toml").write_text("""
[task]
id = "double"
task_class = "x"
difficulty = "T1"
oracle_provenance = "test"

[question]
text = "old"

[expected]
verdict = "unknown"

[questions.q1]
text = "new"
expected_verdict = "unknown"
""")
    problems = matcher.validate_task(bad)
    assert any("both" in p for p in problems)


# === Harness orchestration (dry-run) =====================================


def test_run_one_task_dry_run_returns_one_record_per_question(
    fixture_dir: Path, tmp_path: Path
):
    import harness  # type: ignore
    tasks = harness.discover_tasks(corpus=fixture_dir.parent)
    fixture = next(t for t in tasks if t.id == "fixture-multi-q")

    tx = tmp_path / "_transcripts"
    records = harness.run_one_task(
        task=fixture,
        condition="A",
        model_slot="slot_test",
        seed=0,
        transcripts_dir=tx,
        dry_run=True,
        model_config=None,
        rubric_config=None,
    )
    assert len(records) == 2
    assert records[0].question_id == "q1"
    assert records[1].question_id == "q2"
    # Per-question transcript paths.
    assert "q1" in records[0].transcript_path
    assert "q2" in records[1].transcript_path
    # The dry-run "unknown" verdict fails the matcher (expected="proved")
    # for both questions, but the harness still runs both.
    assert records[0].graded["verdict_correct"] is False
    assert records[1].graded["verdict_correct"] is False
    # Both transcripts must exist on disk.
    assert (tx / records[0].transcript_path).is_file()
    assert (tx / records[1].transcript_path).is_file()


def test_run_one_task_threads_prior_question_context_into_prompt(
    fixture_dir: Path, tmp_path: Path
):
    import harness  # type: ignore
    tasks = harness.discover_tasks(corpus=fixture_dir.parent)
    fixture = next(t for t in tasks if t.id == "fixture-multi-q")

    tx = tmp_path / "_transcripts"
    records = harness.run_one_task(
        task=fixture, condition="A", model_slot="slot_test", seed=0,
        transcripts_dir=tx, dry_run=True,
    )
    # q2's prompt must reference q1's text and verdict (the dry-run
    # observed verdict is "unknown").
    q2_transcript = json.loads((tx / records[1].transcript_path).read_text())
    assert "Prior questions" in q2_transcript["prompt"]
    assert "x18 stays bounded" in q2_transcript["prompt"]
    assert "**unknown**" in q2_transcript["prompt"]  # the threaded verdict
    # And the LearnedFact-injection callout fires.
    assert "injected as a LearnedFact" in q2_transcript["prompt"]
    # q1's prompt has no prior-questions block (empty rendered).
    q1_transcript = json.loads((tx / records[0].transcript_path).read_text())
    assert "Prior questions" not in q1_transcript["prompt"]


def test_assemble_prompt_injects_learned_fact_into_spec(fixture_dir: Path):
    import harness  # type: ignore
    tasks = harness.discover_tasks(corpus=fixture_dir.parent)
    fixture = next(t for t in tasks if t.id == "fixture-multi-q")
    q1, q2 = fixture.questions

    prior_obs = (q1, {"verdict": "proved", "confidence": 0.95,
                       "reason": "x18 ≤ 10 inductively"})
    text, _tools = harness.assemble_prompt(
        fixture, "B", question=q2, prior_observations=[prior_obs],
    )
    # The starter spec block in the prompt must carry the injected
    # LearnedFact (its expression is q.q1.verdict=proved).
    assert '"q.q1.verdict=proved"' in text
    assert '"validated": true' in text  # proved ⇒ validated=true


def test_assemble_prompt_validated_false_when_prior_unproved(fixture_dir: Path):
    import harness  # type: ignore
    tasks = harness.discover_tasks(corpus=fixture_dir.parent)
    fixture = next(t for t in tasks if t.id == "fixture-multi-q")
    q1, q2 = fixture.questions

    prior_obs = (q1, {"verdict": "unreachable", "confidence": 0.7})
    text, _tools = harness.assemble_prompt(
        fixture, "B", question=q2, prior_observations=[prior_obs],
    )
    # unreachable is bounded, not inductive — must NOT promote to
    # validated=true.
    assert '"q.q1.verdict=unreachable"' in text
    assert '"validated": false' in text


def test_run_one_cell_rejects_multi_question(fixture_dir: Path, tmp_path: Path):
    import harness  # type: ignore
    tasks = harness.discover_tasks(corpus=fixture_dir.parent)
    fixture = next(t for t in tasks if t.id == "fixture-multi-q")
    with pytest.raises(ValueError, match="multi-question"):
        harness.run_one_cell(
            task=fixture, condition="A", model_slot="slot_test", seed=0,
            transcripts_dir=tmp_path, dry_run=True,
        )


def test_run_one_question_alone_runs_q1_only(fixture_dir: Path, tmp_path: Path):
    import harness  # type: ignore
    tasks = harness.discover_tasks(corpus=fixture_dir.parent)
    fixture = next(t for t in tasks if t.id == "fixture-multi-q")
    rec = harness.run_one_question(
        task=fixture, question=fixture.questions[0],
        condition="A", model_slot="slot_test", seed=0,
        transcripts_dir=tmp_path, dry_run=True,
    )
    assert rec.question_id == "q1"
    # q1's transcript must exist; q2's must NOT (we ran q1 in isolation).
    assert (tmp_path / rec.transcript_path).is_file()
    assert "q1" in rec.transcript_path
