"""Tests for the Language descriptor + registry (gurdy.core.language)."""

from __future__ import annotations

import pytest

from gurdy.core.language import (
    Language,
    _clear_languages_for_tests,
    get_language,
    list_languages,
    register_language,
)


@pytest.fixture(autouse=True)
def _clean():
    _clear_languages_for_tests()
    yield
    _clear_languages_for_tests()


def test_register_and_lookup():
    lang = Language(
        id="btor2", kind="reasoning", semantics="bit-vector TS", reasons_via=("z3",)
    )
    register_language(lang)
    assert get_language("btor2") is lang
    assert "btor2" in list_languages()


def test_list_filtered_by_kind():
    register_language(Language(id="c", kind="input"))
    register_language(Language(id="rv64-elf", kind="representation"))
    register_language(Language(id="btor2", kind="reasoning"))
    assert list_languages() == ("btor2", "c", "rv64-elf")  # sorted
    assert list_languages(kind="input") == ("c",)
    assert list_languages(kind="reasoning") == ("btor2",)
    assert list_languages(kind="representation") == ("rv64-elf",)


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        Language(id="x", kind="bogus")


def test_list_with_bad_kind_rejected():
    with pytest.raises(ValueError):
        list_languages(kind="bogus")


def test_idempotent_equal_reregister():
    register_language(Language(id="c", kind="input", semantics="C"))
    register_language(Language(id="c", kind="input", semantics="C"))  # equal: ok
    assert get_language("c").kind == "input"


def test_conflicting_reregister_errors():
    register_language(Language(id="c", kind="input"))
    with pytest.raises(ValueError):
        register_language(Language(id="c", kind="representation"))


def test_missing_lookup_raises():
    with pytest.raises(KeyError):
        get_language("nope")
