from dataclasses import dataclass

from gurdy.core.annotation.lookup import IntrospectQuery, query
from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.core.annotation.types import (
    Annotation,
    LearnedFactProvenance,
    NodeProvenance,
    Role,
)


@dataclass(frozen=True)
class _SrcMap:
    pc: int
    line: int


def test_emit_round_trip_through_json():
    side = AnnotationSidecar(schema_version="1.0.0", spec_hash="abc")
    em = AnnotationEmitter(side)
    em.emit("machine", 1, Role.STATE, source_mapping=_SrcMap(pc=0x100, line=42))
    em.emit("constraint", 2, "constraint", source_mapping={"label": "x"})

    js = side.to_json()
    rebuilt = AnnotationSidecar.from_json(js)
    assert rebuilt.schema_version == "1.0.0"
    assert rebuilt.spec_hash == "abc"
    assert len(rebuilt) == 2
    assert rebuilt.entries[0].layer == "machine"
    assert rebuilt.entries[0].role is Role.STATE
    assert rebuilt.entries[1].source_mapping == {"label": "x"}
    assert rebuilt.entries[0].provenance is not None
    assert rebuilt.entries[0].provenance.schema_version == "1.0.0"


def test_learned_fact_provenance_persists():
    side = AnnotationSidecar(schema_version="1.0.0", spec_hash="z")
    side.add(
        Annotation(
            layer="constraint",
            nid=5,
            role=Role.LEARNED_INVARIANT,
            provenance=NodeProvenance(
                schema_version="1.0.0",
                spec_hash="z",
                learned_fact=LearnedFactProvenance(
                    source_question_hash="prev",
                    source_engine="z3-spacer",
                    validated=True,
                ),
            ),
        )
    )
    rebuilt = AnnotationSidecar.from_json(side.to_json())
    a = rebuilt.entries[0]
    assert a.provenance.learned_fact.source_engine == "z3-spacer"
    assert a.provenance.learned_fact.validated is True


def test_query_filters_by_layer_role_and_source_mapping():
    side = AnnotationSidecar(schema_version="1", spec_hash="h")
    em = AnnotationEmitter(side)
    em.emit("machine", 1, Role.STATE, source_mapping={"reg": 1})
    em.emit("machine", 2, Role.STATE, source_mapping={"reg": 2})
    em.emit("constraint", 3, Role.CONSTRAINT)

    by_layer = query(side, IntrospectQuery(layer="machine"))
    assert len(by_layer.matches) == 2

    by_role = query(side, IntrospectQuery(role=Role.CONSTRAINT))
    assert len(by_role.matches) == 1
    assert by_role.matches[0].nid == 3

    by_sm = query(side, IntrospectQuery(layer="machine", source_mapping={"reg": 2}))
    assert len(by_sm.matches) == 1
    assert by_sm.matches[0].nid == 2


def test_content_hash_is_stable():
    side1 = AnnotationSidecar(schema_version="1", spec_hash="h")
    side2 = AnnotationSidecar(schema_version="1", spec_hash="h")
    AnnotationEmitter(side1).emit("a", 1, Role.STATE)
    AnnotationEmitter(side2).emit("a", 1, Role.STATE)
    assert side1.content_hash() == side2.content_hash()
