"""Tests for the interpreter-protocol additions on ``Pair`` / ``register_pair``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest

from gurdy.core.interp import (
    InputBinding,
    ReasoningBinding,
    ReasoningTrace,
    SourceTrace,
)
from gurdy.core.pair import (
    Pair,
    ReasoningInterpreter,
    SourceInterpreter,
    _clear_registry_for_tests,
    register_pair,
)
from gurdy.core.spec.base import BaseSpec


@dataclass(frozen=True)
class _Spec(BaseSpec):
    pair = "_test/interp"


@dataclass(frozen=True)
class _Inp(InputBinding):
    pair: ClassVar[str] = "_test/interp"


@dataclass(frozen=True)
class _ReasInp(ReasoningBinding):
    pair: ClassVar[str] = "_test/interp"


class _SrcInterp:
    def run(self, source, binding, max_steps, *, spec=None):
        return SourceTrace(
            pair="_test/interp",
            interpreter_version="1.0.0",
            inputs_hash=binding.inputs_hash(),
            steps=(),
        )


class _ReasInterp:
    def run(self, artifact, binding, max_steps):
        return ReasoningTrace(
            pair="_test/interp",
            interpreter_version="1.0.0",
            artifact_hash="x",
            bindings_hash=binding.bindings_hash(),
            steps=(),
        )


def _loader(p):
    return ("source", p)


def _validate(spec, source):
    return ()


class _Translator:
    def translate(self, spec, source, em):
        raise NotImplementedError


class _Lifter:
    def lift(self, artifact, raw):
        raise NotImplementedError


class _Solver:
    name = "_solver"

    def dispatch(self, ab, d):
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _clean():
    _clear_registry_for_tests()
    yield
    _clear_registry_for_tests()


def _make(version="0.1.0", with_interp=True):
    return Pair(
        identifier="_test/interp",
        schema_version=version,
        source_loader=_loader,
        spec_class=_Spec,
        spec_validator=_validate,
        layer_specs=(),
        translator=_Translator(),
        lifter=_Lifter(),
        solvers={"_solver": _Solver},
        schema_path=Path("/dev/null"),
        source_interpreter=_SrcInterp() if with_interp else None,
        reasoning_interpreter=_ReasInterp() if with_interp else None,
        interpreter_version="1.0.0" if with_interp else "",
    )


def test_protocols_accept_structural_implementations():
    assert isinstance(_SrcInterp(), SourceInterpreter)
    assert isinstance(_ReasInterp(), ReasoningInterpreter)


def test_register_pair_with_interpreters_succeeds():
    p = _make()
    register_pair(p)


def test_register_pair_without_interpreters_succeeds_when_version_empty():
    p = _make(with_interp=False)
    register_pair(p)


def test_register_pair_rejects_declared_version_without_source_interp():
    p = Pair(
        identifier="_test/interp",
        schema_version="0.1.0",
        source_loader=_loader,
        spec_class=_Spec,
        spec_validator=_validate,
        layer_specs=(),
        translator=_Translator(),
        lifter=_Lifter(),
        solvers={"_solver": _Solver},
        schema_path=Path("/dev/null"),
        source_interpreter=None,
        reasoning_interpreter=_ReasInterp(),
        interpreter_version="1.0.0",
    )
    with pytest.raises(ValueError, match="no source_interpreter"):
        register_pair(p)


def test_register_pair_rejects_declared_version_without_reasoning_interp():
    p = Pair(
        identifier="_test/interp",
        schema_version="0.1.0",
        source_loader=_loader,
        spec_class=_Spec,
        spec_validator=_validate,
        layer_specs=(),
        translator=_Translator(),
        lifter=_Lifter(),
        solvers={"_solver": _Solver},
        schema_path=Path("/dev/null"),
        source_interpreter=_SrcInterp(),
        reasoning_interpreter=None,
        interpreter_version="1.0.0",
    )
    with pytest.raises(ValueError, match="no reasoning_interpreter"):
        register_pair(p)
