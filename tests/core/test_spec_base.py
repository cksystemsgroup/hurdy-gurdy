from dataclasses import dataclass

from gurdy.core.spec.base import (
    BaseAnalysisDirective,
    BaseAssumption,
    BaseObservable,
    BaseProperty,
    BaseSpec,
)


@dataclass(frozen=True)
class _Obs(BaseObservable):
    name: str
    width: int


@dataclass(frozen=True)
class _Spec(BaseSpec):
    pair = "_test_pair"
    name: str = ""
    observables: tuple = ()
    extras: tuple = ()


def test_spec_hash_is_deterministic():
    s1 = _Spec(name="x", observables=(_Obs("a", 8),))
    s2 = _Spec(name="x", observables=(_Obs("a", 8),))
    assert s1.spec_hash() == s2.spec_hash()


def test_spec_hash_changes_with_field():
    s1 = _Spec(name="x", observables=(_Obs("a", 8),))
    s2 = _Spec(name="y", observables=(_Obs("a", 8),))
    assert s1.spec_hash() != s2.spec_hash()


def test_canonical_bytes_is_json():
    import json

    s = _Spec(name="x", observables=(_Obs("a", 8),))
    obj = json.loads(s.canonical_bytes())
    assert obj["pair"] == "_test_pair"


def test_base_analysis_directive_has_engine():
    d = BaseAnalysisDirective(engine="z3-bmc", bound=10, timeout=1.5)
    assert d.engine == "z3-bmc"
    assert d.bound == 10


def test_base_assumption_and_property_inheritable():
    @dataclass(frozen=True)
    class A(BaseAssumption):
        n: int

    @dataclass(frozen=True)
    class P(BaseProperty):
        s: str

    A(1)
    P("ok")
