#!/usr/bin/env python3
"""Witness carry-back: the solver's payload already is the dimacs
interpreter's input format ({"assignment": [...]}), so this is the
identity map. <payload> <program> -> interpreter input on stdout."""
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    sys.stdout.write(fh.read())
