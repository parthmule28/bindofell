from copy import deepcopy

import pytest
from pydantic import ValidationError


def snapshot(payload):
    from bindofell.domain.models import EstateSnapshot

    return EstateSnapshot.model_validate(payload)


def test_snapshot_preserves_missing_metadata_and_is_immutable(estate_payload):
    estate_payload["fields"][0]["attributes"] = {"unusual_label": "NA", "measured": 12}
    estate = snapshot(estate_payload)
    assert estate.fields[0].data_type is None
    assert estate.fields[0].description is None
    assert estate.fields[0].primary_key is None
    assert estate.fields[0].attributes["measured"] == 12
    with pytest.raises(ValidationError):
        estate.snapshot_id = "urn:synthetic:changed"
    with pytest.raises(TypeError):
        estate.fields[0].attributes["unusual_label"] = "changed"


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("duplicate_field", "duplicate field"),
        ("duplicate_table", "duplicate table"),
        ("wrong_id", "canonical field"),
        ("unknown_table", "unknown table"),
        ("namespace", "namespace"),
        ("relationship", "unknown relationship endpoint"),
    ],
)
def test_snapshot_rejects_invalid_identity_and_relationship(estate_payload, mutation, match):
    if mutation == "duplicate_field":
        estate_payload["fields"] *= 2
    elif mutation == "duplicate_table":
        estate_payload["tables"] *= 2
    elif mutation == "wrong_id":
        estate_payload["fields"][0]["field_id"] = "urn:wrong:field"
    elif mutation == "unknown_table":
        estate_payload["tables"] = []
    elif mutation == "namespace":
        estate_payload["dataset"]["namespace"] = "other"
    else:
        estate_payload["relationships"] = [
            {
                "relationship_id": "urn:synthetic:fk",
                "source_field_ids": [estate_payload["fields"][0]["field_id"]],
                "target_field_ids": ["urn:missing:field"],
                "kind": "foreign_key",
            }
        ]
    with pytest.raises(ValidationError, match=match):
        snapshot(estate_payload)


def test_snapshot_accepts_composite_relationship_and_canonicalizes_order(estate_payload):
    from bindofell.domain.models import field_id

    other = deepcopy(estate_payload["fields"][0])
    other["address"]["column"] = "another"
    other["name"] = "another"
    other["field_id"] = field_id("synthetic", "Entity", "another")
    estate_payload["fields"].append(other)
    ids = [f["field_id"] for f in estate_payload["fields"]]
    estate_payload["relationships"] = [
        {
            "relationship_id": "urn:synthetic:fk",
            "source_field_ids": ids,
            "target_field_ids": ids,
            "kind": "foreign_key",
        }
    ]
    estate = snapshot(estate_payload)
    assert tuple(f.field_id for f in estate.fields) == tuple(sorted(ids))
    assert estate.relationships[0].source_field_ids == tuple(ids)


def test_evidence_requires_attribution():
    from bindofell.domain.models import Evidence

    with pytest.raises(ValidationError, match="source evidence"):
        Evidence(evidence_id="urn:synthetic:e", kind="source")
    evidence = Evidence(
        evidence_id="urn:synthetic:e",
        kind="source",
        asset_id="urn:synthetic:f",
        source_locator="fixture.csv:row=2",
        source_digest="a" * 64,
        attribute="description",
        value="Original guidance",
    )
    assert evidence.value == "Original guidance"
    with pytest.raises(ValidationError, match="computation evidence"):
        Evidence(evidence_id="urn:synthetic:e", kind="computation")


def test_binding_contracts_keep_derived_expressions_opaque_and_scores_finite():
    from bindofell.domain.models import BindingCandidate, BusinessRequirement, DerivedBinding

    assert (
        BusinessRequirement(requirement_id="urn:synthetic:q", text="  Verbatim  ").text
        == "  Verbatim  "
    )
    derived = DerivedBinding(
        binding_id="urn:synthetic:b",
        requirement_id="urn:synthetic:q",
        snapshot_id="urn:synthetic:s",
        output_name="future",
        input_field_ids=("urn:synthetic:f",),
        expression_reference="opaque://not-executed",
        grain="person",
    )
    assert derived.kind == "derived"
    for rank, score in [(0, 1.0), (1, float("nan")), (1, float("inf")), (1, True), (1, "1.0")]:
        with pytest.raises(ValidationError):
            BindingCandidate(
                requirement_id="urn:synthetic:q",
                snapshot_id="urn:synthetic:s",
                field_id="urn:synthetic:f",
                rank=rank,
                raw_score=score,
                method_id="synthetic",
            )


def test_optional_qualifiers_roundtrip_and_remain_distinct(estate_payload):
    from bindofell.domain.models import FieldAddress, PhysicalField, Table, TableAddress

    tables, fields = [], []
    for qualifiers in ({"schema": "x"}, {"catalog": "x"}, {}):
        address = TableAddress.model_validate(
            {"namespace": "synthetic", "table": "Entity", **qualifiers}
        )
        field_address = FieldAddress.model_validate({**address.model_dump(), "column": "key"})
        tables.append(Table(table_id=address.table_id, name="Entity", address=address))
        fields.append(
            PhysicalField(
                field_id=field_address.field_id,
                table_id=address.table_id,
                name="key",
                address=field_address,
            )
        )
    estate_payload["tables"] = [t.model_dump() for t in tables]
    estate_payload["fields"] = [f.model_dump() for f in fields]
    estate = snapshot(estate_payload)
    assert len({f.field_id for f in estate.fields}) == 3
    assert snapshot(estate.model_dump()) == estate


def test_relationship_rejects_mismatched_composite_key_lengths():
    from bindofell.domain.models import Relationship

    with pytest.raises(ValidationError, match="equal lengths"):
        Relationship(
            relationship_id="urn:synthetic:r",
            kind="foreign_key",
            source_field_ids=("urn:synthetic:a", "urn:synthetic:b"),
            target_field_ids=("urn:synthetic:c",),
        )


def test_direct_binding_discriminator_and_attributed_computation():
    from pydantic import TypeAdapter

    from bindofell.domain.models import Evidence, SemanticBinding

    adapter = TypeAdapter(SemanticBinding)
    value = {
        "kind": "direct",
        "binding_id": "urn:synthetic:b",
        "requirement_id": "urn:synthetic:q",
        "snapshot_id": "urn:synthetic:s",
        "field_id": "urn:synthetic:f",
    }
    assert adapter.validate_python(value).kind == "direct"
    with pytest.raises(ValidationError):
        adapter.validate_python({**value, "kind": "unknown"})
    evidence = Evidence(
        evidence_id="urn:synthetic:e",
        kind="computation",
        computation="serialize",
        computation_version="1",
        input_ids=("urn:synthetic:f",),
        parameters={"profile": "names"},
    )
    assert evidence.parameters["profile"] == "names"
