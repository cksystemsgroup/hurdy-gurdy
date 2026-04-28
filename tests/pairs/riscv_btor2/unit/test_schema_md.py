from pathlib import Path

from gurdy.core.schema.indexer import load_index


SCHEMA = Path(__file__).resolve().parents[3].parent / "gurdy/pairs/riscv_btor2/SCHEMA.md"


def test_schema_md_parses_and_has_required_sections():
    idx = load_index("riscv-btor2", SCHEMA)
    headings = set(idx.topics())
    # The schema's H2s are numbered ("1. Versioning", ...). We assert
    # presence of recognizable substrings, since the indexer also
    # supports substring lookup.
    must_have_substrings = [
        "Versioning",
        "Sorts",
        "State variables",
        "ELF loading",
        "Instruction lowering",
        "Dispatch",
        "Entry assumptions",
        "Constraint and bad encoding",
        "Havoc semantics",
        "Verdict semantics",
    ]
    for needle in must_have_substrings:
        assert any(needle in h for h in headings), (
            f"SCHEMA.md missing section containing {needle!r}; "
            f"headings={sorted(headings)}"
        )


def test_schema_describe_returns_body():
    idx = load_index("riscv-btor2", SCHEMA)
    # Substring lookup will hit "2. Sorts".
    e = idx.describe("Sorts")
    assert e is not None
    # Either an exact body or a hint pointing at it.
    assert "bv64" in e.body or e.hint


def test_schema_addi_subsection_resolves_or_substring_hint():
    idx = load_index("riscv-btor2", SCHEMA)
    e = idx.describe("LUI")
    assert e is not None
    assert "LUI" in e.heading or e.hint  # at least produces an answer
