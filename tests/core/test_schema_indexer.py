from textwrap import dedent

from gurdy.core.schema.indexer import load_index, parse_schema, slugify


SAMPLE = dedent(
    """\
    # Sample Pair Schema

    Top-level introduction.

    ## Sorts

    Bitvector and array sorts go here.

    ## Instruction Lowering

    Per-mnemonic body.

    ### ADDI

    Sign-extends imm12, adds to rs1, writes to rd.

    ### XOR

    Bitwise xor.

    ## Verdict Semantics

    What reachable / unreachable mean.
    """
)


def test_slugify_normalizes():
    assert slugify("Hello, World") == "hello-world"
    assert slugify("ADDI") == "addi"
    assert slugify("a/b c") == "a-b-c"


def test_parse_schema_flattens_h1_title():
    sections = parse_schema(SAMPLE)
    headings = [s.heading for s in sections]
    assert headings == [
        "Sorts",
        "Instruction Lowering",
        "Verdict Semantics",
    ]
    instr = sections[1]
    assert [s.heading for s in instr.subsections] == ["ADDI", "XOR"]
    assert "Sign-extends" in instr.subsections[0].body


def test_parse_schema_no_title_keeps_h2_top_level():
    text = "## A\n\nbody a\n\n## B\n\nbody b\n"
    sections = parse_schema(text)
    assert [s.heading for s in sections] == ["A", "B"]


def test_index_describe_exact_match(tmp_path):
    p = tmp_path / "SCHEMA.md"
    p.write_text(SAMPLE)
    idx = load_index("test-pair", p)
    e = idx.describe("ADDI")
    assert e is not None
    assert e.heading == "ADDI"
    assert "Sign-extends" in e.body
    assert e.hint is None


def test_index_describe_slug(tmp_path):
    p = tmp_path / "SCHEMA.md"
    p.write_text(SAMPLE)
    idx = load_index("test-pair", p)
    e = idx.describe("instruction-lowering")
    assert e is not None
    assert e.heading == "Instruction Lowering"
    assert "ADDI" in e.subheadings


def test_index_describe_substring_unique(tmp_path):
    p = tmp_path / "SCHEMA.md"
    p.write_text(SAMPLE)
    idx = load_index("test-pair", p)
    e = idx.describe("verdict")
    assert e is not None
    assert e.heading == "Verdict Semantics"


def test_index_describe_miss_returns_hint(tmp_path):
    p = tmp_path / "SCHEMA.md"
    p.write_text(SAMPLE)
    idx = load_index("test-pair", p)
    e = idx.describe("verify")
    assert e is not None
    assert e.body == ""
    assert e.hint is not None
