"""Which lines of one script ran: ``cover.py <out> <script> [args...]``.

Runs ``script`` as the program it is, with its own arguments, and
appends the line numbers it executed to ``out`` as one JSON list. The
harness puts this in front of the executable under test while the
intact entry is gated, so that every mutant can be told apart: a fault
on a line no admission input ever reaches survives because nothing
looked, not because the gate looked and missed.
"""

import atexit
import json
import runpy
import sys

_out, _script = sys.argv[1], sys.argv[2]
sys.argv = sys.argv[2:]
_hit: set[int] = set()
_mon = sys.monitoring
_tool = _mon.COVERAGE_ID


def _line(code, line):
    if code.co_filename == _script:
        _hit.add(line)
    return _mon.DISABLE


def _dump():
    with open(_out, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(sorted(_hit)) + "\n")


_mon.use_tool_id(_tool, "faults")
_mon.register_callback(_tool, _mon.events.LINE, _line)
_mon.set_events(_tool, _mon.events.LINE)
atexit.register(_dump)
runpy.run_path(_script, run_name="__main__")
