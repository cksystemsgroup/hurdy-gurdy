import pytest

from gurdy.core.layers.declaration import (
    LayerDependencyError,
    order_layers,
    required_dependencies,
)
from gurdy.core.layers.linker import (
    LayerRecord,
    LinkerSyntax,
    LinkInput,
    LinkError,
    link,
)
from gurdy.core.pair import LayerSpec


def test_order_layers_topologically():
    specs = (
        LayerSpec(name="a", stability="universal"),
        LayerSpec(name="b", stability="universal", depends_on=("a",)),
        LayerSpec(name="c", stability="universal", depends_on=("b",)),
    )
    o = order_layers(specs)
    assert o.order == ("a", "b", "c")


def test_order_layers_breaks_ties_by_declaration_order():
    specs = (
        LayerSpec(name="x", stability="u"),
        LayerSpec(name="y", stability="u"),
        LayerSpec(name="z", stability="u", depends_on=("x", "y")),
    )
    o = order_layers(specs)
    assert o.order[:2] == ("x", "y")
    assert o.order[2] == "z"


def test_order_layers_rejects_cycle():
    specs = (
        LayerSpec(name="a", stability="u", depends_on=("b",)),
        LayerSpec(name="b", stability="u", depends_on=("a",)),
    )
    with pytest.raises(LayerDependencyError):
        order_layers(specs)


def test_order_layers_rejects_undeclared_dep():
    specs = (LayerSpec(name="a", stability="u", depends_on=("missing",)),)
    with pytest.raises(LayerDependencyError):
        order_layers(specs)


def test_required_dependencies_transitive():
    specs = (
        LayerSpec(name="a", stability="u"),
        LayerSpec(name="b", stability="u", depends_on=("a",)),
        LayerSpec(name="c", stability="u", depends_on=("b",)),
    )
    deps = set(required_dependencies(specs, "c"))
    assert deps == {"a", "b"}


# ---------- linker ----------


def _parse(layer: str, body: bytes) -> list[LayerRecord]:
    """Synthetic line-oriented format for tests:

    Each line is ``NID OP[,ARG[,ARG...]][;@export NAME][;@import NAME]``.
    Refs are local nids referenced by ARG ints; imports pull from
    other layers.
    """

    out: list[LayerRecord] = []
    for line in body.decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        directives = ""
        if ";@" in line:
            payload, directives = line.split(";@", 1)
        else:
            payload = line
        head = payload.strip().split(" ", 1)
        nid_s = head[0]
        rest = head[1] if len(head) > 1 else ""
        nid = int(nid_s)
        op_args = rest.split(",")
        op = op_args[0]
        refs: list[int] = []
        for arg in op_args[1:]:
            arg = arg.strip()
            if arg.startswith("#"):
                refs.append(int(arg[1:]))
        exports: list[str] = []
        imports: list[str] = []
        if directives:
            for d in directives.split(";@"):
                d = d.strip()
                if d.startswith("export "):
                    exports.append(d.removeprefix("export ").strip())
                elif d.startswith("import "):
                    imports.append(d.removeprefix("import ").strip())
        out.append(
            LayerRecord(
                nid=nid,
                raw=(op, op_args),
                refs=tuple(refs),
                exports=tuple(exports),
                imports=tuple(imports),
            )
        )
    return out


def _print(rec: LayerRecord) -> bytes:
    op, _ = rec.raw  # type: ignore[misc]
    parts = [str(rec.nid), op]
    for r in rec.refs:
        parts.append(f"#{r}")
    return ",".join(parts).encode("utf-8")


def test_link_resolves_imports_across_layers():
    specs = (
        LayerSpec(name="header", stability="universal"),
        LayerSpec(name="machine", stability="u", depends_on=("header",)),
    )
    syntax = LinkerSyntax(parser=_parse, printer=_print)
    inputs = [
        LinkInput(name="header", bytes_=b"1 sort_bv32;@export bv32\n"),
        LinkInput(name="machine", bytes_=b"1 state;@import bv32\n"),
    ]
    res = link(specs, inputs, syntax)
    text = res.flattened.decode("utf-8")
    # header gets nid 1; machine record's import is resolved to global nid 1;
    # machine record itself is renumbered to global nid 2.
    assert "1,sort_bv32" in text
    assert "2,state,#1" in text
    assert res.nid_map["machine"][1] == 2
    assert res.nid_map["header"][1] == 1


def test_link_double_export_errors():
    specs = (LayerSpec(name="a", stability="u"),)
    syntax = LinkerSyntax(parser=_parse, printer=_print)
    inputs = [
        LinkInput(name="a", bytes_=b"1 op;@export X\n2 op;@export X\n"),
    ]
    with pytest.raises(LinkError):
        link(specs, inputs, syntax)


def test_link_unresolved_import_errors():
    specs = (LayerSpec(name="a", stability="u"),)
    syntax = LinkerSyntax(parser=_parse, printer=_print)
    inputs = [LinkInput(name="a", bytes_=b"1 op;@import nope\n")]
    with pytest.raises(LinkError):
        link(specs, inputs, syntax)
