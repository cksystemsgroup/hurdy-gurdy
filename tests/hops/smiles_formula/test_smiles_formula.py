"""Tests for the smiles-formula transparent compile pair (chemistry).

Pure-Python and dependency-free (no Docker). Exercises correctness against
hand-computed molecular formulas (the predictability invariant), subset
rejection, determinism, and integration with the generic graph machinery
(routes / Chain / recompile_and_diff)."""

from __future__ import annotations

import pytest

from gurdy.hops.smiles_formula import (
    MOLECULAR_FORMULA_LANG,
    SMILES_FORMULA,
    SMILES_LANG,
    SmilesError,
    smiles_to_formula,
)


@pytest.fixture(autouse=True)
def _register():
    # Re-register (idempotent) so the graph tests below find the hop and its
    # languages even when another test module cleared the global registries.
    from gurdy.core.hop import register_hop
    from gurdy.core.language import register_language

    register_hop(SMILES_FORMULA)
    register_language(SMILES_LANG)
    register_language(MOLECULAR_FORMULA_LANG)
    yield


@pytest.mark.parametrize(
    "smiles,formula",
    [
        ("C", "CH4"),  # methane
        ("CC", "C2H6"),  # ethane
        ("CCO", "C2H6O"),  # ethanol
        ("C=C", "C2H4"),  # ethene
        ("C#C", "C2H2"),  # ethyne
        ("O", "H2O"),  # water (no carbon -> alphabetical)
        ("N", "H3N"),  # ammonia
        ("O=C=O", "CO2"),  # carbon dioxide
        ("CC(=O)O", "C2H4O2"),  # acetic acid (branch + double bond)
        ("CC#N", "C2H3N"),  # acetonitrile
        ("C1CCCCC1", "C6H12"),  # cyclohexane (ring closure)
        ("C1=CC=CC=C1", "C6H6"),  # benzene, Kekulé form
        ("CCl", "CH3Cl"),  # chloromethane (two-letter element)
        ("ClC(Cl)(Cl)Cl", "CCl4"),  # carbon tetrachloride
        ("CSC", "C2H6S"),  # dimethyl sulfide (S valence 2)
        ("CS(=O)(=O)C", "C2H6O2S"),  # dimethyl sulfone (S valence 6)
    ],
)
def test_known_molecules(smiles, formula):
    assert smiles_to_formula(smiles) == formula


def test_bytes_input():
    assert smiles_to_formula(b"CCO") == "C2H6O"


def test_whitespace_stripped():
    assert smiles_to_formula("  CCO\n") == "C2H6O"


@pytest.mark.parametrize(
    "bad",
    [
        "c1ccccc1",  # aromatic lowercase
        "[CH4]",  # bracket atom
        "C.C",  # disconnected
        "(C)",  # branch with no preceding atom
        ")",  # unmatched close
        "C=",  # dangling bond
        "C1CC",  # unclosed ring
        "C(C",  # unclosed branch
        "%",  # unsupported char
        "Xx",  # unknown element
        "",  # empty
    ],
)
def test_subset_rejected(bad):
    with pytest.raises(SmilesError):
        smiles_to_formula(bad)


def test_deterministic():
    assert smiles_to_formula("CC(=O)O") == smiles_to_formula("CC(=O)O") == "C2H4O2"


def test_registered_in_graph():
    from gurdy.core.hop import get_hop, list_hops
    from gurdy.core.language import list_languages

    assert "smiles-formula" in list_hops(kind="compile")
    hop = get_hop("smiles-formula")
    assert (hop.in_lang, hop.out_lang) == ("smiles", "molecular-formula")
    assert hop.tier.value == "transparent"
    assert "smiles" in list_languages(kind="input")
    assert "molecular-formula" in list_languages(kind="representation")


def test_routes_and_chain_determinism():
    from gurdy.core.chain import Chain, ChainStep, StepOutcome, recompile_and_diff
    from gurdy.core.route import routes

    (r,) = routes("smiles", "molecular-formula")
    assert r.hops == ("smiles-formula",)
    assert r.trust.value == "transparent"
    assert r.is_deterministic is True
    assert r.predictable_prefix == 1  # the whole (one-hop) chain is predictable

    chain = Chain(
        [
            ChainStep(
                hop="smiles-formula",
                in_lang="smiles",
                out_lang="molecular-formula",
                run=lambda s: StepOutcome(
                    output=smiles_to_formula(s), provenance={"formula": smiles_to_formula(s)}
                ),
            )
        ]
    )
    assert chain.run("CCO").final == "C2H6O"
    assert recompile_and_diff(chain, "CCO").deterministic is True
