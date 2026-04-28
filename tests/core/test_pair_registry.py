from dataclasses import dataclass
from pathlib import Path

import pytest

from gurdy.core.pair import (
    Lifter,
    Pair,
    SolverBackend,
    SourceLoader,
    SpecValidator,
    Translator,
    _clear_registry_for_tests,
    get_pair,
    list_pairs,
    register_pair,
)
from gurdy.core.spec.base import BaseSpec


@dataclass(frozen=True)
class _Spec(BaseSpec):
    pair = "_test/dummy"


def _loader(payload):
    return ("source", payload)


def _validator(spec, source):
    return ()


class _Translator:
    def translate(self, spec, source, annotation_emitter):
        raise NotImplementedError


class _Lifter:
    def lift(self, artifact, raw):
        raise NotImplementedError


class _Solver:
    name = "_solver"

    def dispatch(self, artifact_bytes, directive):
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _clean():
    _clear_registry_for_tests()
    yield
    _clear_registry_for_tests()


def _make_pair(identifier="_test/dummy", schema_version="0.1.0"):
    return Pair(
        identifier=identifier,
        schema_version=schema_version,
        source_loader=_loader,
        spec_class=_Spec,
        spec_validator=_validator,
        layer_specs=(),
        translator=_Translator(),
        lifter=_Lifter(),
        solvers={"_solver": _Solver},
        schema_path=Path("/dev/null"),
    )


def test_register_and_lookup_roundtrip():
    p = _make_pair()
    register_pair(p)
    assert get_pair("_test/dummy") is p
    assert "_test/dummy" in list_pairs()


def test_double_register_same_object_is_idempotent():
    p = _make_pair()
    register_pair(p)
    register_pair(p)
    assert get_pair("_test/dummy") is p


def test_double_register_different_version_errors():
    register_pair(_make_pair(schema_version="0.1.0"))
    with pytest.raises(ValueError):
        register_pair(_make_pair(schema_version="0.2.0"))


def test_lookup_missing_raises():
    with pytest.raises(KeyError):
        get_pair("nope")


def test_protocols_accept_structural_mocks():
    assert isinstance(_loader, SourceLoader)
    assert isinstance(_validator, SpecValidator)
    assert isinstance(_Translator(), Translator)
    assert isinstance(_Lifter(), Lifter)
    assert isinstance(_Solver(), SolverBackend)
