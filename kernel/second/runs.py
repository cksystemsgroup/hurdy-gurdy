"""Benchmark and log loading (KERNEL.md §5) for the second lineage."""

import hashlib
import json
import os


class BenchmarkError(Exception):
    """A hard error while loading a benchmark (exit status 1)."""


def load_benchmark(run_dir):
    """Load ``<run-dir>/benchmark.json`` and re-verify every program pin."""
    path = os.path.join(run_dir, "benchmark.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            bench = json.load(f)
    except (OSError, ValueError) as e:
        raise BenchmarkError(f"{path}: unreadable benchmark: {e}")
    questions = bench.get("questions")
    if not isinstance(questions, list):
        raise BenchmarkError(f"{path}: no questions list")
    for q in questions:
        program = os.path.join(run_dir, q.get("program", ""))
        try:
            with open(program, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
        except OSError as e:
            raise BenchmarkError(f"{program}: pinned program unreadable: {e}")
        if digest != q.get("sha256"):
            raise BenchmarkError(
                f"{program}: pin violation for question {q.get('id')}: "
                f"pinned {q.get('sha256')}, found {digest}"
            )
    if "name" not in bench:
        bench["name"] = os.path.basename(os.path.normpath(run_dir))
    return bench


def load_log(run_dir):
    """Read ``<run-dir>/log.jsonl`` in order; a missing log is empty."""
    path = os.path.join(run_dir, "log.jsonl")
    records = []
    if not os.path.exists(path):
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records
