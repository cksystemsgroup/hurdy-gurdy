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
    from gurdy.core.tools.dispatch import dispatch as _dispatch
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


# === REAL: condition C's solver subprocess wrapper ========================


# bitwuzla and cvc5 ship in the bench image as Python-binding-only
# wheels — there's no CLI binary in PATH. Condition C exposes only
# the engines that have a real CLI: z3 and pono.
_SOLVE_ALLOWED = {
    ("z3",   "smt2"),
    ("pono", "btor2"),
}


def tool_solve(
    engine: str,
    input_language: str,
    input_text: str,
    options: dict | None = None,
) -> dict:
    """Run a pinned solver binary on hand-written input.

    Each (engine, input_language) pair in the allowed set runs the
    same solver the riscv-btor2 pair would dispatch to under
    condition B, but the LLM under condition C is responsible for
    producing the `input_text` itself — no translation help, no
    schema, no annotation. See `prompts/tools_c.json` for the
    contract.

    SMT2 engines (z3, bitwuzla, cvc5):
      - Invoked as `<engine> -in` (read SMT-LIB2 from stdin).
      - We append `(check-sat)` only if the input doesn't already
        end in one (cooperative; LLM may forget).
      - Verdict is the last `sat` / `unsat` / `unknown` token in
        stdout.

    BTOR2 engine (pono):
      - Invoked as `pono -e bmc -k <bound> --btor /dev/stdin`.
      - `bound` from options.bound; default 10.
      - Verdict is `sat` (= reachable) / `unsat` (= unreachable) /
        anything else (= unknown).

    `options.timeout` (seconds, default 30) is passed to
    subprocess.run as a timeout; on TimeoutExpired the verdict is
    `unknown` with a `timed out` reason.
    """
    import os as _os
    import shutil
    import subprocess
    import time as _time

    options = dict(options or {})
    if (engine, input_language) not in _SOLVE_ALLOWED:
        return {
            "verdict": "error",
            "stdout": "",
            "stderr": f"(engine={engine!r}, input_language={input_language!r}) not allowed",
            "elapsed": 0.0,
        }

    timeout = float(options.get("timeout", 30.0))
    start = _time.monotonic()

    import tempfile

    payload = input_text
    btor_tmp: str | None = None

    if engine == "pono":
        bound = int(options.get("bound", 10))
        # Pono detects format by file extension and won't read /dev/stdin
        # (rejected as "Unrecognized file extension"). Stage the input
        # in a temp .btor2 file.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".btor2", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(payload)
            btor_tmp = tf.name
        argv = ["pono", "-e", "bmc", "-k", str(bound), btor_tmp]
    elif engine == "z3":
        argv = ["z3", "-in"]
        if input_language == "smt2" and "(check-sat)" not in payload:
            payload = payload.rstrip() + "\n(check-sat)\n"
            if options.get("produce_models"):
                payload = "(set-option :produce-models true)\n" + payload + "(get-model)\n"
    else:
        return {
            "verdict": "error",
            "stdout": "",
            "stderr": f"engine {engine!r} not supported as CLI",
            "elapsed": 0.0,
        }

    if shutil.which(argv[0]) is None:
        if btor_tmp:
            try: _os.unlink(btor_tmp)
            except OSError: pass
        return {
            "verdict": "error",
            "stdout": "",
            "stderr": f"binary {argv[0]!r} not found in PATH",
            "elapsed": _time.monotonic() - start,
        }

    try:
        result = subprocess.run(
            argv,
            input=payload if engine != "pono" else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        if btor_tmp:
            try: _os.unlink(btor_tmp)
            except OSError: pass
        return {
            "verdict": "unknown",
            "stdout": (e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""))[:4096],
            "stderr": "timed out",
            "elapsed": _time.monotonic() - start,
        }
    finally:
        if btor_tmp:
            try: _os.unlink(btor_tmp)
            except OSError: pass

    elapsed = _time.monotonic() - start
    out = result.stdout
    err = result.stderr

    # Parse verdict: prefer the last sat/unsat/unknown token in stdout.
    verdict = "unknown"
    for tok in reversed(out.split()):
        if tok in ("sat", "unsat", "unknown"):
            verdict = tok
            break
    if verdict == "unknown" and result.returncode != 0 and not out.strip():
        # Outright failure with no parseable output.
        return {
            "verdict": "error",
            "stdout": out[:4096],
            "stderr": err[:4096],
            "elapsed": elapsed,
        }

    return {
        "verdict": verdict,
        "stdout":  out[:8192],
        "stderr":  err[:2048],
        "elapsed": elapsed,
    }


# === REAL: LLM adapters (anthropic + openai) ===============================


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

    `tools` is in Anthropic format (name/description/input_schema)
    matching prompts/tools_b.json and tools_c.json. The OpenAI adapter
    converts; the Anthropic adapter passes through.

    `on_tool_call(name, input_dict) -> result_dict` is provided by
    the run driver; for condition B it dispatches to B_TOOLS, for
    condition C it dispatches to tool_solve. The adapter just hands
    the vendor's parsed name+input to it and feeds the result back
    into the next turn.
    """
    if family == "anthropic":
        return _call_anthropic(model_id, system_or_user_text, tools, params, seed, on_tool_call)
    if family == "openai":
        return _call_openai(model_id, system_or_user_text, tools, params, seed, on_tool_call)
    if family == "google":
        return _call_google(model_id, system_or_user_text, tools, params, seed, on_tool_call)
    if family == "claude-code":
        return _call_claude_code(model_id, system_or_user_text, tools, params, seed, on_tool_call)
    raise NotImplementedError(
        f"call_llm not implemented for family={family!r}. Add a vendor adapter "
        "that loops over tool_use turns and returns LLMResponse."
    )


def _call_claude_code(model_id, prompt, tools, params, seed, on_tool_call):
    """Invoke the local ``claude`` CLI in non-interactive mode.

    Uses the operator's existing Claude Code authentication (OAuth via
    keychain, or whatever auth is wired into the CLI), so no separate
    vendor API key is required. Each cell is one isolated subprocess.

    Tool surface: condition A only. Conditions B and C would require
    exposing ``B_TOOLS`` / ``tool_solve`` to the spawned Claude session
    via an MCP server -- that work is intentionally not in this adapter.
    Calling with non-empty ``tools`` raises NotImplementedError so the
    caller fails loudly rather than silently dropping the tool surface.

    Recognized ``params`` keys:
      - ``timeout`` (int, default 600): subprocess wall-clock cap.
      - ``extra_args`` (list[str]): forwarded verbatim to ``claude``.
        Useful for ``--add-dir``, ``--append-system-prompt``, etc.
    """
    import shutil
    import subprocess

    if tools:
        raise NotImplementedError(
            "claude-code adapter supports condition A only (tools=None). "
            "B/C tool surfaces would need an MCP server that re-exposes "
            "B_TOOLS / tool_solve to the subprocess; not implemented."
        )

    cli = shutil.which("claude")
    if cli is None:
        raise RuntimeError(
            "`claude` CLI not on PATH. Install Claude Code and ensure the "
            "binary is reachable, or pick a different model_slot in llms.md."
        )

    timeout = int(params.get("timeout", 600))
    extra_args: list[str] = list(params.get("extra_args", []))
    # When this harness itself runs inside a Claude Code session, the
    # parent process injects ANTHROPIC_API_KEY pointing at a key that
    # may be exhausted / not the operator's actual account. Strip
    # those env vars from the child unless the operator explicitly
    # opts in via params['inherit_env']=True, so the spawned `claude`
    # falls through to its own keychain OAuth login.
    inherit_env = bool(params.get("inherit_env", False))
    import os as _os
    child_env = dict(_os.environ)
    if not inherit_env:
        for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            child_env.pop(var, None)

    # The CLI's --disallowedTools flag is variadic ('<tools...>' in
    # commander.js), which greedily consumes any subsequent positional
    # argument. Passing the prompt positionally after --disallowedTools
    # therefore loses the prompt entirely ("Input must be provided
    # either through stdin or as a prompt argument when using --print").
    # Pipe the prompt via stdin to sidestep that.
    cmd = [
        cli,
        "--print",
        "--output-format", "json",
        "--model", model_id,
        "--no-session-persistence",
        "--disable-slash-commands",
        # The LLM under condition A is supposed to reason from the prompt
        # alone -- no Bash, no file reads, nothing.
        "--disallowedTools",
        "Bash,Read,Edit,Write,WebFetch,WebSearch,Grep,Glob,Agent,Task,NotebookEdit,Skill",
        *extra_args,
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        return LLMResponse(
            text=f"(claude --print timed out after {timeout}s)",
            final_json={"verdict": "unknown", "confidence": 0.0,
                        "reason": "claude-code subprocess timeout",
                        "witness": None, "lift": None},
            tool_calls=[],
        )

    # The CLI's --output-format json envelope wraps the assistant's final
    # text in a result field plus usage stats. Try to parse it before
    # interpreting the exit code -- the CLI exits non-zero on
    # is_error=true (credit exhausted, quota, model overload), but the
    # structured error is only readable from the JSON body.
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    if not payload:
        # No parseable envelope; fall back to rc + stderr.
        return LLMResponse(
            text=f"(claude --print exited {proc.returncode}: {proc.stderr[:400]})",
            final_json={"verdict": "unknown", "confidence": 0.0,
                        "reason": f"claude-code subprocess rc={proc.returncode}",
                        "witness": None, "lift": None},
            tool_calls=[],
        )

    text = (
        payload.get("result")
        or payload.get("text")
        or payload.get("content")
        or ""
    )
    # The CLI returns is_error=true with a structured error string in
    # `result` for credit / quota / model-overload failures (the
    # envelope itself parses fine but the inference never ran). Surface
    # those as `unknown` so downstream grading sees the same shape it
    # gets from a vendor-side error rather than parsing the error
    # string as the assistant's verdict.
    if payload.get("is_error") or payload.get("subtype") == "error":
        reason = text or payload.get("error") or "claude-code reported is_error"
        return LLMResponse(
            text=f"(claude --print returned is_error: {reason})",
            final_json={"verdict": "unknown", "confidence": 0.0,
                        "reason": f"claude-code: {reason[:200]}",
                        "witness": None, "lift": None},
            tool_calls=[],
        )

    usage = payload.get("usage") or {}
    return LLMResponse(
        text=text,
        final_json=extract_final_json(text),
        tool_calls=[],
        tokens_in=int(usage.get("input_tokens", 0) or 0),
        tokens_out=int(usage.get("output_tokens", 0) or 0),
        tokens_cached=int(usage.get("cache_read_input_tokens", 0) or 0),
    )


def _call_anthropic(model_id, prompt, tools, params, seed, on_tool_call):
    """Anthropic Messages API multi-turn tool-use loop."""
    import anthropic

    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": prompt}]
    tokens_in = tokens_out = tokens_cached = 0
    tool_calls: list[dict] = []
    max_turns = int(params.get("max_turns", 8))

    last_text = ""
    for _turn in range(max_turns):
        kwargs: dict[str, Any] = {
            "model": model_id,
            "max_tokens": int(params.get("max_tokens", 16384)),
            "temperature": float(params.get("temperature", 0.7)),
            "top_p": float(params.get("top_p", 0.95)),
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        resp = client.messages.create(**kwargs)
        u = resp.usage
        tokens_in += u.input_tokens
        tokens_out += u.output_tokens
        tokens_cached += int(getattr(u, "cache_read_input_tokens", 0) or 0)

        last_text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")

        if resp.stop_reason != "tool_use":
            return LLMResponse(
                text=last_text,
                final_json=extract_final_json(last_text),
                tool_calls=tool_calls,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                tokens_cached=tokens_cached,
            )

        # Tool-use turn: execute every tool_use block, append results.
        messages.append({"role": "assistant", "content": resp.content})
        results: list[dict] = []
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            result = on_tool_call(block.name, dict(block.input))
            tool_calls.append({"name": block.name, "input": dict(block.input), "result": result})
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )
        messages.append({"role": "user", "content": results})

    # max_turns exhausted without an end_turn stop_reason.
    return LLMResponse(
        text=last_text or "(max_turns reached)",
        final_json=extract_final_json(last_text),
        tool_calls=tool_calls,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_cached=tokens_cached,
    )


def _anthropic_tools_to_openai(tools: list[dict] | None) -> list[dict] | None:
    """Translate {name, description, input_schema} -> OpenAI's
    {type:'function', function:{name, description, parameters}}."""
    if not tools:
        return None
    out: list[dict] = []
    for t in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object"}),
                },
            }
        )
    return out


def _call_openai(model_id, prompt, tools, params, seed, on_tool_call):
    """OpenAI Chat Completions multi-turn tool-use loop.

    Honors `params['base_url']` and `params['api_key_env']` so the
    same adapter can route through OpenAI-compatible providers
    (e.g., GitHub Models at https://models.github.ai/inference with
    a `models:read`-scoped GitHub PAT in `GITHUB_TOKEN`). For the
    canonical scored runs `params` should leave both unset and the
    SDK uses OPENAI_API_KEY against the OpenAI endpoint — the
    snapshot pinning the run manifest is keyed on requires the
    vendor's own dated id.
    """
    import os as _os
    from openai import OpenAI

    base_url = params.get("base_url")
    api_key_env = params.get("api_key_env")
    client_kwargs: dict[str, Any] = {}
    if base_url:
        client_kwargs["base_url"] = base_url
    if api_key_env:
        key = _os.environ.get(api_key_env)
        if key:
            client_kwargs["api_key"] = key
    client = OpenAI(**client_kwargs)
    messages: list[dict] = [{"role": "user", "content": prompt}]
    oai_tools = _anthropic_tools_to_openai(tools)
    tokens_in = tokens_out = tokens_cached = 0
    tool_calls: list[dict] = []
    max_turns = int(params.get("max_turns", 8))

    # Newer OpenAI models (gpt-5+, reasoning models) require
    # max_completion_tokens instead of max_tokens; the SDK accepts
    # max_completion_tokens for older models too. Use the new name
    # uniformly.
    last_text = ""
    for _turn in range(max_turns):
        kwargs: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": float(params.get("temperature", 0.7)),
            "top_p": float(params.get("top_p", 0.95)),
            "max_completion_tokens": int(params.get("max_tokens", 16384)),
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"
        if seed:
            kwargs["seed"] = int(seed)

        resp = client.chat.completions.create(**kwargs)
        u = resp.usage
        tokens_in += u.prompt_tokens
        tokens_out += u.completion_tokens
        tokens_cached += int(getattr(u, "prompt_tokens_details", None).cached_tokens
                             if getattr(u, "prompt_tokens_details", None) else 0) or 0

        msg = resp.choices[0].message
        last_text = msg.content or ""

        if not msg.tool_calls:
            return LLMResponse(
                text=last_text,
                final_json=extract_final_json(last_text),
                tool_calls=tool_calls,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                tokens_cached=tokens_cached,
            )

        # Tool calls: append assistant message + per-call results.
        assistant_msg: dict = {
            "role": "assistant",
            "content": msg.content or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        }
        messages.append(assistant_msg)
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            result = on_tool_call(tc.function.name, args)
            tool_calls.append({"name": tc.function.name, "input": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                }
            )

    return LLMResponse(
        text=last_text or "(max_turns reached)",
        final_json=extract_final_json(last_text),
        tool_calls=tool_calls,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_cached=tokens_cached,
    )


def _anthropic_tools_to_google(tools: list[dict] | None):
    """Translate {name, description, input_schema} -> Google's
    google.genai.types.Tool with function_declarations.

    Returns None if tools is empty.
    """
    if not tools:
        return None
    from google.genai import types as gtypes

    decls: list[Any] = []
    for t in tools:
        decls.append(
            gtypes.FunctionDeclaration(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("input_schema") or {"type": "object"},
            )
        )
    return [gtypes.Tool(function_declarations=decls)]


def _call_google(model_id, prompt, tools, params, seed, on_tool_call):
    """Google Gemini multi-turn function-calling loop via the new
    google-genai SDK.

    Auth: GOOGLE_API_KEY (default) or GEMINI_API_KEY (also accepted by
    the SDK). For Vertex routing pass `params["vertex_project"]` and
    `params["vertex_location"]`; not implemented here yet.

    Multi-turn shape: the SDK exchanges `Content` objects (role +
    list of `Part`s). A function-call turn appears as a part with
    `function_call` set; we run on_tool_call and append a part with
    `function_response` for the next turn.
    """
    from google import genai
    from google.genai import types as gtypes

    client_kwargs: dict[str, Any] = {}
    api_key_env = params.get("api_key_env")
    if api_key_env:
        import os as _os
        key = _os.environ.get(api_key_env)
        if key:
            client_kwargs["api_key"] = key
    client = genai.Client(**client_kwargs)

    google_tools = _anthropic_tools_to_google(tools)

    # Conversation contents — accumulate as we loop.
    contents: list[Any] = [
        gtypes.Content(role="user", parts=[gtypes.Part(text=prompt)])
    ]

    cfg_kwargs: dict[str, Any] = {
        "temperature": float(params.get("temperature", 0.7)),
        "top_p": float(params.get("top_p", 0.95)),
        "max_output_tokens": int(params.get("max_tokens", 16384)),
    }
    if google_tools:
        cfg_kwargs["tools"] = google_tools
    if seed:
        cfg_kwargs["seed"] = int(seed)
    config = gtypes.GenerateContentConfig(**cfg_kwargs)

    tokens_in = tokens_out = tokens_cached = 0
    tool_calls: list[dict] = []
    max_turns = int(params.get("max_turns", 8))
    last_text = ""

    for _turn in range(max_turns):
        resp = client.models.generate_content(
            model=model_id,
            contents=contents,
            config=config,
        )
        u = getattr(resp, "usage_metadata", None)
        if u is not None:
            tokens_in += int(getattr(u, "prompt_token_count", 0) or 0)
            tokens_out += int(getattr(u, "candidates_token_count", 0) or 0)
            tokens_cached += int(getattr(u, "cached_content_token_count", 0) or 0)

        candidate = (resp.candidates or [None])[0]
        parts = candidate.content.parts if candidate and candidate.content else []
        text_parts = [p.text for p in parts if getattr(p, "text", None)]
        last_text = "".join(text_parts)
        fcalls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        if not fcalls:
            return LLMResponse(
                text=last_text,
                final_json=extract_final_json(last_text),
                tool_calls=tool_calls,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                tokens_cached=tokens_cached,
            )

        # Tool-call turn: append the model's content, then a user
        # content with one function_response part per call.
        contents.append(candidate.content)
        response_parts: list[Any] = []
        for fc in fcalls:
            args = dict(fc.args) if fc.args else {}
            result = on_tool_call(fc.name, args)
            tool_calls.append({"name": fc.name, "input": args, "result": result})
            response_parts.append(
                gtypes.Part.from_function_response(name=fc.name, response=result)
            )
        contents.append(gtypes.Content(role="user", parts=response_parts))

    return LLMResponse(
        text=last_text or "(max_turns reached)",
        final_json=extract_final_json(last_text),
        tool_calls=tool_calls,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_cached=tokens_cached,
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

    response_text = ""
    tool_call_log: list[dict] = []
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
        response_text = "(dry-run stub)"
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
        response_text = resp.text
        tool_call_log = list(resp.tool_calls)
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
                "prompt":         text,
                "tools":          tools,
                "response_text":  response_text,
                "tool_call_log":  tool_call_log,
                "observed":       observed,
                "seed":           seed,
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


# === Model registry =======================================================
#
# Mirrors `llms.md`'s pinned inventory in machine-readable form. The CLI
# resolves --model against this table; entries are kept in sync with
# llms.md by hand. A future revision may parse llms.md directly, but
# the prose-plus-table format there is hard to parse robustly and a
# small Python dict suffices for v0.1.x.
MODELS: dict[str, dict] = {
    # Slot A — see llms.md "Slot A — Google Gemini Flash". Active for
    # v0.1.1 single-vendor exploratory runs. Requires GOOGLE_API_KEY.
    "slot_A": {
        "family":   "google",
        "model_id": "gemini-2.5-flash",
        "params": {
            "temperature": 0.7,
            "top_p":       0.95,
            "max_tokens":  16384,
            "max_turns":   8,
            "api_key_env": "GOOGLE_API_KEY",
        },
    },
    # Slot CC — see llms.md "Slot CC — Claude Code subprocess".
    # No vendor API key required; uses the local `claude` CLI's auth.
    # Condition A only -- _call_claude_code raises NotImplementedError
    # if invoked with tools (B/C surfaces).
    "slot_CC": {
        "family":   "claude-code",
        "model_id": "claude-opus-4-7",
        "params": {
            "timeout":    600,
            "extra_args": [],
        },
    },
    # Rubric LLM — see llms.md "Rubric LLM — OpenAI via GitHub Models".
    # Used by the §9.7 rubric grading path, not as a model under test.
    "rubric": {
        "family":   "openai",
        "model_id": "openai/gpt-4.1-mini",
        "params": {
            "temperature": 0.0,
            "top_p":       1.0,
            "max_tokens":  4096,
            "max_turns":   1,
            "base_url":    "https://models.github.ai/inference",
            "api_key_env": "GITHUB_TOKEN",
        },
    },
}


# === CLI ==================================================================


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--list-tasks", action="store_true")
    p.add_argument("--list-models", action="store_true")
    p.add_argument("--task")
    p.add_argument("--condition", choices=["A", "B", "C"])
    p.add_argument("--model", help=f"Slot id, one of: {sorted(MODELS)}")
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

    if args.list_models:
        for slot in sorted(MODELS):
            cfg = MODELS[slot]
            print(f"{slot:10}  family={cfg['family']:12}  model_id={cfg['model_id']}")
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

    model_config: dict | None = None
    if not args.dry_run:
        if args.model not in MODELS:
            p.error(f"--model {args.model!r} not in MODELS; available: {sorted(MODELS)}")
        model_config = MODELS[args.model]

    task = task_by_id(tasks, args.task)
    record = run_one_cell(
        task=task,
        condition=args.condition,
        model_slot=args.model,
        seed=args.seed,
        transcripts_dir=args.transcripts_dir,
        dry_run=args.dry_run,
        model_config=model_config,
    )
    print(json.dumps(asdict(record), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
