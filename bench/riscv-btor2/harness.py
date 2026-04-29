"""Harness skeleton for the riscv-btor2 benchmark.

Wires the §9.x pre-registered artifacts (corpus, prompts, llms,
rubric, manifest schema, determinism check) into a single runner that
turns "for every (task, condition, model_slot, seed) cell, run the
session and grade it" into a §9.8 run manifest.

This file is a STUB. The pieces in ``# === REAL ===`` sections are
implemented; the pieces in ``# === STUBBED ===`` sections raise
NotImplementedError with a specific message about what to fill in.
The boundary is the LLM API call and Condition C's solver subprocess
wrapping — everything else (prompt assembly, gurdy delegation for
Condition B, grading via rubric/matcher.py, manifest building) is
real and exercisable.

Dry-run mode (``--dry-run``) walks the full pipeline without making
LLM calls: it assembles the prompt, prints it, fabricates a trivial
``unknown``-verdict response, grades it, and produces a manifest
record. Useful for testing wiring before any vendor work lands.

Usage examples:

    # Discover tasks and exit
    python harness.py --list-tasks

    # Dry-run a single cell (no API calls)
    python harness.py --task 0001-x0-write-dropped --condition A \\
                      --model slot_A --seed 42 --dry-run

    # Real run (raises NotImplementedError until LLM adapters land)
    python harness.py --task 0001-x0-write-dropped --condition A \\
                      --model slot_A --seed 42

    # Build manifest from a directory of completed run JSONs
    python harness.py --build-manifest <dir>

Pre-registration checklist (BENCHMARKING.md §9):

  9.1 SCOPE.md         — committed
  9.2 corpus/          — 2 seed tasks; ≥ 30 needed before runs
  9.3 prompts/         — committed
  9.4 baseline         — D omitted, documented
  9.5 solver inventory — image christophkirsch/hurdy-gurdy-bench
  9.6 llms.md          — Slot A locked, Slot B TBD
  9.7 rubric/          — matcher real; rubric-LLM prompt TODO
  9.8 manifest_schema  — committed
  9.9 check_determinism— committed

Item 4 (this harness) is NOT pre-registration; it is implementation.
Pre-registering an empty harness is meaningless. The pre-reg tag
covers everything in §9.1–§9.9; this file lands separately and may
evolve freely until the first scored run.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = Path(__file__).resolve().parent
CORPUS = BENCH_ROOT / "corpus"
PROMPTS = BENCH_ROOT / "prompts"
RUBRIC = BENCH_ROOT / "rubric"


# === REAL: task discovery ==================================================


@dataclass
class Task:
    id: str
    dir: Path
    raw: dict[str, Any]  # parsed task.toml
    spec: dict[str, Any]  # parsed spec.json

    @property
    def expected_verdict(self) -> str:
        return self.raw["expected"]["verdict"]

    @property
    def difficulty(self) -> str:
        return self.raw["task"]["difficulty"]


def discover_tasks(corpus: Path = CORPUS) -> list[Task]:
    tasks: list[Task] = []
    for d in sorted(corpus.iterdir()):
        if not d.is_dir():
            continue
        if not (d / "task.toml").is_file():
            continue
        with (d / "task.toml").open("rb") as f:
            raw = tomllib.load(f)
        with (d / "spec.json").open() as f:
            spec = json.load(f)
        tasks.append(Task(id=raw["task"]["id"], dir=d, raw=raw, spec=spec))
    return tasks


def task_by_id(tasks: list[Task], tid: str) -> Task:
    matches = [t for t in tasks if t.id == tid or t.dir.name == tid]
    if not matches:
        raise SystemExit(f"no task matched {tid!r}; --list-tasks to see options")
    if len(matches) > 1:
        raise SystemExit(f"{tid!r} ambiguous: {[t.id for t in matches]}")
    return matches[0]


# === REAL: prompt assembly =================================================


def _disasm_for(task: Task) -> str:
    """Read source.S inline; the harness doesn't shell out to objdump
    since the bench image's content is already pinned. The {{DISASSEMBLY}}
    placeholder gets the raw `objdump -d` output verbatim — the harness
    is expected to run `make` first so source.elf exists.

    For the stub we just emit a marker; replace with the actual
    objdump call before the first scored run."""
    elf = task.dir / "source.elf"
    if not elf.is_file():
        return f"<source.elf not built; run `make -C bench/riscv-btor2/corpus` first>"
    import subprocess
    try:
        out = subprocess.check_output(
            ["riscv64-unknown-elf-objdump", "-d", str(elf)],
            stderr=subprocess.STDOUT,
        ).decode()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return f"<objdump unavailable: {e}>"
    # Drop the file-format header lines; keep the disassembly proper.
    return "\n".join(line for line in out.splitlines() if line.strip())


def _starter_spec_for(spec: dict[str, Any]) -> dict[str, Any]:
    """Strip property + witness from the task's spec.json. The LLM
    under condition B must derive these from the question."""
    starter = json.loads(json.dumps(spec))  # deep copy
    fields = starter.setdefault("fields", {})
    fields.pop("property", None)
    return starter


def assemble_prompt(task: Task, condition: str) -> tuple[str, list[dict] | None]:
    """Return (full_system_prompt_or_user_prompt, tools_or_none).

    The full prompt is the concatenation of _base.md and the per-
    condition file with {{...}} substituted. tools is the JSON loaded
    from tools_b.json or tools_c.json (None for condition A).
    """
    if condition not in ("A", "B", "C"):
        raise ValueError(f"condition must be A/B/C, got {condition!r}")

    base = (PROMPTS / "_base.md").read_text()
    condfile = (PROMPTS / f"condition_{condition.lower()}.md").read_text()
    text = base + "\n\n" + condfile

    subs: dict[str, str] = {
        "{{TASK_ID}}":           task.id,
        "{{QUESTION_TEXT}}":     task.raw["question"]["text"].strip(),
        "{{SOURCE_S}}":          (task.dir / "source.S").read_text().rstrip(),
        "{{DISASSEMBLY}}":       _disasm_for(task),
        "{{PAIR_ID}}":           "riscv-btor2",
        "{{SCHEMA_URL}}": "https://github.com/christophkirsch/hurdy-gurdy/blob/main/gurdy/pairs/riscv_btor2/SCHEMA.md",
        "{{STARTER_SPEC_JSON}}": json.dumps(_starter_spec_for(task.spec), indent=2),
    }
    for k, v in subs.items():
        text = text.replace(k, v)

    tools: list[dict] | None = None
    if condition in ("B", "C"):
        with (PROMPTS / f"tools_{condition.lower()}.json").open() as f:
            tools = json.load(f)
    return text, tools


# === REAL: condition B's tool surface (gurdy delegation) ===================


def tool_compile(spec_obj: dict) -> dict:
    """Delegate to gurdy.core.tools.compile.compile_spec."""
    from gurdy.core.tools.compile import compile_spec
    from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
    from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec

    spec = RiscvBtor2Spec.from_jsonable(spec_obj)
    artifact = compile_spec(spec)
    # Stash the artifact, the source it was compiled against, and the
    # raw spec so subsequent dispatch / lift calls find them without
    # re-serializing or re-loading.
    _ARTIFACT_CACHE[artifact.spec_hash] = artifact
    if spec.binary.path:
        try:
            _SOURCE_CACHE[artifact.spec_hash] = load_riscv_binary(spec.binary.path)
        except Exception:
            pass  # lift will degrade gracefully without source
    return {
        "artifact_id": artifact.spec_hash,
        "schema_version": artifact.schema_version,
        "byte_length": len(artifact.flattened),
        "diagnostics": [],
    }


_ARTIFACT_CACHE: dict[str, Any] = {}
_SOURCE_CACHE: dict[str, Any] = {}
_RAW_CACHE: dict[str, Any] = {}  # last RawSolverResult per artifact_id


def tool_dispatch(artifact_id: str, directive: dict) -> dict:
    from gurdy.core.dispatch.dispatch import dispatch as _dispatch
    from gurdy.pairs.riscv_btor2.spec import AnalysisDirective, Comparison  # noqa: F401

    artifact = _ARTIFACT_CACHE.get(artifact_id)
    if artifact is None:
        return {"verdict": "error", "reason": f"unknown artifact_id {artifact_id!r}"}
    havoc = frozenset(int(r) for r in directive.get("havoc_registers", []))
    d = AnalysisDirective(
        engine=directive["engine"],
        bound=directive.get("bound"),
        timeout=directive.get("timeout"),
        havoc_registers=havoc,
        extra_options=dict(directive.get("extra_options", {})),
    )
    raw = _dispatch(artifact, d)
    _RAW_CACHE[artifact_id] = raw
    return {
        "verdict": raw.verdict,
        "engine":  raw.engine,
        "elapsed": raw.elapsed,
        "reason":  raw.reason,
        # payload is intentionally not surfaced to the LLM; lift looks
        # it up from _RAW_CACHE[artifact_id] when called.
    }


def tool_lift(artifact_id: str, raw_result: dict) -> dict:
    from gurdy.core.dispatch.result import RawSolverResult
    from gurdy.pairs.riscv_btor2.lift.lift import Lifter

    artifact = _ARTIFACT_CACHE.get(artifact_id)
    if artifact is None:
        return {"error": f"unknown artifact_id {artifact_id!r}"}

    # Prefer the cached RawSolverResult (carries the witness payload
    # bytes that we deliberately don't surface to the LLM); fall back
    # to a synthesized result built from the LLM-passed fields.
    raw = _RAW_CACHE.get(artifact_id)
    if raw is None:
        raw = RawSolverResult(
            verdict=raw_result["verdict"],
            elapsed=raw_result.get("elapsed", 0.0),
            engine=raw_result.get("engine", ""),
            reason=raw_result.get("reason"),
            payload=None,
        )

    source = _SOURCE_CACHE.get(artifact_id)
    lifted = Lifter().lift(artifact, raw, source=source)
    return {
        "verdict": lifted.verdict,
        "trace": [
            {"cycle": s.cycle, "pc": s.pc, "mnemonic": s.mnemonic,
             "file": s.file, "line": s.line, "regs": list(s.regs)}
            for s in (lifted.trace.steps if lifted.trace else [])
        ],
        "halted": bool(lifted.trace.halted) if lifted.trace else False,
        "final_regs": list(lifted.trace.final_regs) if lifted.trace else [],
    }


def tool_introspect(spec_obj: dict) -> dict:
    from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec, validate_riscv_btor2_spec
    from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary

    spec = RiscvBtor2Spec.from_jsonable(spec_obj)
    try:
        source = load_riscv_binary(Path(spec.binary.path))
    except Exception as e:
        return {"diagnostics": [{"severity": "error", "code": "loader", "message": str(e)}]}
    return {
        "diagnostics": [
            {"severity": str(d.severity), "code": d.code, "message": d.message}
            for d in validate_riscv_btor2_spec(spec, source)
        ]
    }


B_TOOLS = {
    "compile":    tool_compile,
    "dispatch":   tool_dispatch,
    "lift":       tool_lift,
    "introspect": tool_introspect,
}


# === STUBBED: condition C's solver subprocess wrapping =====================


def tool_solve(engine: str, input_language: str, input_text: str, options: dict | None = None) -> dict:
    """Run a pinned solver binary on hand-written input.

    Stub. Real implementation needs to:
      - Validate (engine, input_language) is in the allowed set.
      - Invoke the solver via subprocess with stdin = input_text.
      - Time it, capture stdout/stderr, parse the verdict.
      - For SMT2 engines: use `(check-sat)` output convention.
      - For pono: pass --btor and -k from options.bound; parse "sat"/"unsat".
      - Honor options.timeout via subprocess.run(timeout=...).
    """
    raise NotImplementedError(
        "tool_solve is the harness side of condition C — wire it to "
        "subprocess invocation of {z3, bitwuzla, cvc5, pono} when "
        "implementing the real run loop."
    )


# === STUBBED: LLM adapter ==================================================


@dataclass
class LLMResponse:
    text: str
    final_json: dict | None
    tool_calls: list[dict] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0


def call_llm(
    *,
    family: str,
    model_id: str,
    system_or_user_text: str,
    tools: list[dict] | None,
    params: dict,
    seed: int,
    on_tool_call,
) -> LLMResponse:
    """Run a single multi-turn session with the configured model.

    Stub. Real implementation per family:

      anthropic: anthropic.Anthropic().messages.create(...) with
                 tools=tools and tool_choice='auto'; loop on tool_use
                 stop_reason, calling `on_tool_call(name, input)` and
                 feeding the result back as a tool_result block.
      openai:    OpenAI().responses.create(model=..., tools=tools,
                 input=...) similarly; vendor differences in tool
                 schema (input_schema → parameters) live in the
                 adapter, not the prompts.
      google:    google.generativeai.GenerativeModel(...).generate_content
                 with function declarations.

    `on_tool_call(name, input_dict) -> result_dict` is provided by
    the harness; for condition B it dispatches to B_TOOLS, for
    condition C it dispatches to tool_solve.

    Token counts must match the vendor's reported numbers and feed
    into the §9.8 manifest's run rows.
    """
    raise NotImplementedError(
        f"call_llm not implemented for family={family!r}. Add a vendor "
        "adapter that loops over tool_use turns and returns LLMResponse."
    )


# === REAL: extract final answer JSON =======================================


def extract_final_json(text: str) -> dict | None:
    """Pull the LAST ```json ... ``` fenced block from the LLM's reply.
    Returns None if no parseable block is found."""
    import re
    blocks = re.findall(r"```json\s*\n(.*?)\n```", text, flags=re.DOTALL)
    for b in reversed(blocks):
        try:
            return json.loads(b)
        except json.JSONDecodeError:
            continue
    return None


# === REAL: grading hand-off to rubric/matcher.py ===========================


def grade(task: Task, observed: dict) -> dict:
    """Run the deterministic matcher against the LLM's observed answer.
    For T4 tasks, the rubric LLM call would land here too; left to the
    same TODO as call_llm."""
    sys.path.insert(0, str(RUBRIC))
    import matcher  # type: ignore
    report = matcher.match(task.dir, observed)
    out = report.to_jsonable()
    if task.difficulty == "T4":
        out["lift_score"] = None  # TODO: rubric-LLM call lands here
    return out


# === REAL: per-cell run record + manifest assembly =========================


@dataclass
class RunRecord:
    task_id: str
    condition: str
    model_slot: str
    seed: int
    started_at: str
    ended_at: str
    transcript_path: str
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    tool_calls: int
    solver_seconds: float
    graded: dict[str, Any]


def now_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_manifest(
    runs: list[RunRecord],
    *,
    corpus_tag: str,
    corpus_commit: str,
    schema_version: str,
    image_digest: str,
    image_tag: str,
    solvers: dict,
    models: dict,
    hardware: dict,
    determinism_check: dict,
    rubric_llm: dict | None = None,
    coverage_gaps: list[str] | None = None,
    notes: str = "",
) -> dict:
    return {
        "benchmark": {
            "pair":           "riscv-btor2",
            "corpus_tag":     corpus_tag,
            "corpus_commit":  corpus_commit,
            "schema_version": schema_version,
            "started_at":     min(r.started_at for r in runs) if runs else now_z(),
            "ended_at":       max(r.ended_at for r in runs) if runs else now_z(),
        },
        "image": {
            "repository": "christophkirsch/hurdy-gurdy-bench",
            "tag":        image_tag,
            "digest":     image_digest,
        },
        "solvers":           solvers,
        "models":            models,
        **({"rubric_llm": rubric_llm} if rubric_llm else {}),
        "hardware":          hardware,
        "determinism_check": determinism_check,
        "runs":              [asdict(r) for r in runs],
        "coverage_gaps":     coverage_gaps or [],
        **({"notes": notes} if notes else {}),
    }


# === Run driver (orchestrates the above) ===================================


def run_one_cell(
    *,
    task: Task,
    condition: str,
    model_slot: str,
    seed: int,
    transcripts_dir: Path,
    dry_run: bool,
    model_config: dict | None = None,
) -> RunRecord:
    started = now_z()
    text, tools = assemble_prompt(task, condition)

    if dry_run:
        # Synthesize a deterministic "unknown" answer so the rest of the
        # pipeline can be exercised without API access.
        observed = {
            "verdict":    "unknown",
            "confidence": 0.5,
            "reason":     "dry-run stub",
            "witness":    None,
            "lift":       None,
        }
        tokens_in = len(text)
        tokens_out = 0
        tokens_cached = 0
        tool_calls = 0
        solver_seconds = 0.0
    else:
        if model_config is None:
            raise SystemExit("--model requires a model_config in real runs (load from llms.md)")

        def on_tool_call(name: str, payload: dict) -> dict:
            if condition == "B":
                fn = B_TOOLS.get(name)
                if not fn:
                    return {"error": f"unknown tool {name!r}"}
                return fn(**payload) if not isinstance(payload, list) else fn(*payload)
            elif condition == "C":
                if name != "solve":
                    return {"error": f"unknown tool {name!r}"}
                return tool_solve(**payload)
            return {"error": f"no tools allowed under condition {condition}"}

        resp = call_llm(
            family=model_config["family"],
            model_id=model_config["model_id"],
            system_or_user_text=text,
            tools=tools,
            params=model_config["params"],
            seed=seed,
            on_tool_call=on_tool_call,
        )
        observed = resp.final_json or {"verdict": "unknown", "confidence": 0.0}
        tokens_in = resp.tokens_in
        tokens_out = resp.tokens_out
        tokens_cached = resp.tokens_cached
        tool_calls = len(resp.tool_calls)
        solver_seconds = 0.0  # TODO: accumulate from B's dispatch / C's solve

    # Persist the transcript.
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    rel = Path(task.id) / condition / model_slot / f"seed-{seed}.json"
    transcript_path = transcripts_dir / rel
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(
        json.dumps(
            {
                "prompt": text,
                "tools":  tools,
                "observed": observed,
                "seed":   seed,
            },
            indent=2,
        )
    )
    ended = now_z()

    return RunRecord(
        task_id=task.id,
        condition=condition,
        model_slot=model_slot,
        seed=seed,
        started_at=started,
        ended_at=ended,
        transcript_path=str(rel),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_cached=tokens_cached,
        tool_calls=tool_calls,
        solver_seconds=solver_seconds,
        graded=grade(task, observed),
    )


# === CLI ==================================================================


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--list-tasks", action="store_true")
    p.add_argument("--task")
    p.add_argument("--condition", choices=["A", "B", "C"])
    p.add_argument("--model", help="Slot id, e.g. slot_A")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--transcripts-dir", type=Path, default=Path("./_transcripts"))
    p.add_argument("--build-manifest", type=Path, help="Build a manifest from a directory of completed run records")
    args = p.parse_args(argv[1:])

    tasks = discover_tasks()
    if args.list_tasks:
        for t in tasks:
            print(f"{t.id:32}  {t.difficulty:3}  expected={t.expected_verdict}")
        return 0

    if args.build_manifest:
        # Stub for the build-manifest path; real impl reads run records
        # written by run_one_cell back from disk.
        raise NotImplementedError(
            "build_manifest path not implemented; use the build_manifest "
            "function directly with a list of RunRecords."
        )

    if not (args.task and args.condition and args.model):
        p.error("--task, --condition, --model are required (or pass --list-tasks)")

    task = task_by_id(tasks, args.task)
    record = run_one_cell(
        task=task,
        condition=args.condition,
        model_slot=args.model,
        seed=args.seed,
        transcripts_dir=args.transcripts_dir,
        dry_run=args.dry_run,
    )
    print(json.dumps(asdict(record), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
