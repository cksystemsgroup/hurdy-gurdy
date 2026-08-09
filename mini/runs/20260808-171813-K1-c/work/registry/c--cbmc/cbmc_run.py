"""Shared helper: drive the cbmc binary and interpret its JSON output.
Independent of csubset.py (registry/c--z3sym) -- this is a disjoint
lineage, engine-adapter style, not a from-scratch decision procedure.
"""
import json
import os
import shutil
import subprocess
import tempfile


def _signed_from_binary(bits):
    v = int(bits, 2)
    return v - (1 << 32) if v >= (1 << 31) else v


def _extract_nondet_values(trace):
    vals = []
    for step in trace:
        if (step.get("stepType") == "assignment"
                and step.get("lhs") == "return_value_nondet_int"
                and not step.get("hidden", False)):
            value = step.get("value", {})
            data = value.get("data")
            try:
                vals.append(int(data))
            except (TypeError, ValueError):
                vals.append(_signed_from_binary(value.get("binary", "0")))
    return vals


def run_cbmc(c_path, unwind, wall_s):
    """Runs cbmc, checking only the user assertion (--no-standard-checks
    drops overflow/bounds/etc.) with unwinding-assertions at the given
    bound. Returns the parsed JSON result array, or None on failure."""
    cmd = ["cbmc", c_path, "--no-standard-checks", "--unwind", str(unwind),
           "--unwinding-assertions", "--json-ui", "--trace"]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=wall_s)
    except subprocess.TimeoutExpired:
        return None
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return None


def classify(data):
    """-> (assertion_failure_trace_or_None, unwind_insufficient: bool,
    error_message_or_None)"""
    props = []
    for item in data or []:
        if isinstance(item, dict) and "result" in item:
            props = item["result"]
    if not props:
        msgs = [item.get("messageText", "") for item in (data or [])
                if isinstance(item, dict) and item.get("messageType") == "ERROR"]
        return None, False, "; ".join(msgs)[:200] or "no result in cbmc output"
    assertion_failures = [p for p in props
                          if p.get("sourceLocation", {}).get("propertyClass")
                          == "assertion" and p.get("status") == "FAILURE"]
    unwind_failures = [p for p in props
                       if ".unwind." in p.get("property", "")
                       and p.get("status") == "FAILURE"]
    if assertion_failures:
        return _extract_nondet_values(assertion_failures[0].get("trace", [])), \
            bool(unwind_failures), None
    return None, bool(unwind_failures), None


def with_c_extension(program_path, scratch_dir):
    c_path = os.path.join(scratch_dir, "prog.c")
    shutil.copyfile(program_path, c_path)
    return c_path
