import json
from pathlib import Path

import pytest

from bindofell.domain.models import field_id
from bindofell.metadata.loader import load_snapshot

FIXTURES = Path(__file__).parents[2] / "fixtures" / "benchmark"


def inputs():
    from bindofell.benchmark.io import make_universe

    snapshot = load_snapshot(FIXTURES / "toy_estate.json")
    return snapshot, make_universe(snapshot)


def records():
    return [json.loads(s) for s in (FIXTURES / "toy_cases.jsonl").read_text().splitlines()]


def text(values):
    return "".join(json.dumps(v) + "\n" for v in values)


def test_strict_jsonl_roundtrip_order_and_digest():
    from bindofell.benchmark.io import cases_digest, cases_from_jsonl, cases_to_jsonl, load_cases

    snapshot, universe = inputs()
    cases = load_cases(FIXTURES / "toy_cases.jsonl", snapshot, universe)
    canonical = cases_to_jsonl(reversed(cases))
    assert cases_from_jsonl(canonical, snapshot, universe) == cases
    assert cases_digest(cases) == cases_digest(reversed(cases))
    assert [c.case_id for c in cases] == sorted(c.case_id for c in cases)
    assert universe.digest == inputs()[1].digest
    assert make_subset_digest(snapshot) != universe.digest


def make_subset_digest(snapshot):
    from bindofell.benchmark.io import make_universe

    return make_universe(
        snapshot, field_ids=(snapshot.fields[0].field_id,), rule_id="urn:toy:eligibility:subset"
    ).digest


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("duplicate_key", "duplicate JSON key"),
        ("nan", "non-finite"),
        ("duplicate_case", "duplicate case"),
        ("version", "schema_version"),
        ("gold_version", "schema_version"),
        ("snapshot", "snapshot"),
        ("absent", "outside snapshot"),
        ("partial", "ineligible"),
        ("clarification", "outside snapshot"),
        ("provenance", "authoring_basis"),
        ("extra", "Extra inputs"),
        ("blank", "blank"),
        ("not_object", "object"),
    ],
)
def test_io_errors_have_line_and_case_context(mutation, match):
    from bindofell.benchmark.io import cases_from_jsonl, make_universe

    snapshot, universe = inputs()
    values = records()
    if mutation == "duplicate_case":
        values.append(values[0])
    elif mutation in ("version", "gold_version"):
        target = values[0] if mutation == "version" else values[0]["gold"]
        target["schema_version"] = "unsupported"
    elif mutation == "snapshot":
        values[0]["snapshot_id"] = "urn:toy:wrong"
    elif mutation in ("absent", "clarification"):
        n = 2 if mutation == "clarification" else 0
        original = field_id("toy", "Alpha", "key")
        replaced = "urn:toy:missing"
        values[n] = json.loads(json.dumps(values[n]).replace(original, replaced))
    elif mutation == "partial":
        universe = make_universe(
            snapshot,
            field_ids=(field_id("toy", "Alpha", "key"),),
            rule_id="urn:toy:eligibility:subset",
        )
    elif mutation == "provenance":
        del values[0]["authoring_basis"]
    elif mutation == "extra":
        values[0]["new"] = "unknown"
    data = text(values)
    if mutation == "duplicate_key":
        data = data.replace('"case_id":', '"case_id":"urn:toy:duplicate","case_id":', 1)
    elif mutation == "nan":
        data = data.replace('"case_id":', '"invalid":NaN,"case_id":', 1)
    elif mutation == "blank":
        data = "\n" + data
    elif mutation == "not_object":
        data = "[]\n"
    with pytest.raises(ValueError, match=match) as error:
        cases_from_jsonl(data, snapshot, universe, source="fixture.jsonl")
    assert "fixture.jsonl:line=" in str(error.value)
    if mutation not in ("duplicate_key", "nan", "blank", "not_object"):
        assert "urn:toy:case:" in str(error.value)


def test_invalid_utf8(tmp_path):
    from bindofell.benchmark.io import load_cases

    path = tmp_path / "bad.jsonl"
    path.write_bytes(b"\xff\n")
    with pytest.raises(ValueError, match="bad.jsonl:line=1.*UTF-8"):
        load_cases(path, *inputs())


def test_universe_rejects_duplicates_unknowns_wrong_snapshot_and_ambiguous_policy():
    from bindofell.benchmark.io import EligibleUniverse, make_universe, validate_universe

    snapshot, universe = inputs()
    with pytest.raises(ValueError, match="duplicate"):
        make_universe(snapshot, field_ids=(snapshot.fields[0].field_id,) * 2)
    with pytest.raises(ValueError, match="outside snapshot"):
        make_universe(snapshot, field_ids=("urn:toy:missing",))
    with pytest.raises(ValueError, match="snapshot"):
        validate_universe(universe, snapshot.model_copy(update={"snapshot_id": "urn:toy:other"}))
    assert EligibleUniverse.model_validate_json(universe.model_dump_json()) == universe


def test_unresolved_cases_can_be_archived_but_not_scored():
    from bindofell.benchmark.io import cases_from_jsonl, validate_cases

    snapshot, universe = inputs()
    values = records()[:1]
    values[0]["review_state"] = "unresolved"
    cases = cases_from_jsonl(text(values), snapshot, universe)
    with pytest.raises(ValueError, match="unresolved.*urn:toy:case:1"):
        validate_cases(cases, snapshot, universe, require_resolved=True)


def test_jsonl_roundtrip_preserves_unicode_line_separator_characters():
    from bindofell.benchmark.io import cases_from_jsonl, cases_to_jsonl

    snapshot, universe = inputs()
    values = records()
    values[0]["requirement"]["text"] = "Original\u0085wording\u2028with\u2029separators"
    cases = cases_from_jsonl(text(values), snapshot, universe)
    assert cases_from_jsonl(cases_to_jsonl(cases), snapshot, universe) == cases


def test_all_fields_policy_cannot_claim_a_subset():
    from bindofell.benchmark.io import make_universe

    snapshot, _ = inputs()
    with pytest.raises(ValueError, match="all-physical-fields.*complete"):
        make_universe(snapshot, field_ids=(snapshot.fields[0].field_id,))


def original_evidence_inputs():
    """A real toy asset record, not a fabricated source-evidence checker."""
    snapshot, universe = inputs()
    value = records()[0]
    data = snapshot.model_dump(mode="json")
    for source in value["gold"]["evidence"]:
        asset = next(f for f in data["fields"] if f["field_id"] == source["asset_id"])
        source["value"] = asset["description"]
        asset["evidence"] = [dict(source)]
    from bindofell.domain.models import EstateSnapshot

    return EstateSnapshot.model_validate(data), universe, value


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("unknown_asset", "asset"),
        ("unknown_digest", "digest"),
        ("changed_locator", "original evidence"),
        ("changed_attribute", "original evidence"),
        ("changed_value", "original evidence"),
        ("rebound_original_id", "original evidence"),
        ("unknown_rejected", "outside snapshot"),
    ],
)
def test_gold_source_evidence_must_agree_with_snapshot(mutation, match):
    from bindofell.benchmark.io import cases_from_jsonl

    snapshot, universe, value = original_evidence_inputs()
    # First prove the unmodified source records are accepted.
    assert cases_from_jsonl(text([value]), snapshot, universe)
    source = value["gold"]["evidence"][0]
    if mutation == "unknown_asset":
        value["gold"]["evidence"].append(
            {**source, "evidence_id": "urn:toy:extra:evidence", "asset_id": "urn:toy:missing"}
        )
    elif mutation == "unknown_digest":
        source["source_digest"] = "b" * 64
    elif mutation == "changed_locator":
        source["source_locator"] = "synthetic://invented/row=99"
    elif mutation == "changed_attribute":
        source["attribute"] = "invented_attribute"
    elif mutation == "changed_value":
        source["value"] = "Invented source meaning"
    elif mutation == "rebound_original_id":
        source["evidence_id"] = value["gold"]["evidence"][1]["evidence_id"]
        value["gold"]["evidence"].pop()
        value["gold"]["accepted_field_ids"] = [source["asset_id"]]
    else:
        missing = "urn:toy:missing:rejection"
        value["gold"]["rejected_candidates"] = [{"field_id": missing, "rationale": "Wrong entity"}]
        value["gold"]["evidence"].append(
            {**source, "evidence_id": "urn:toy:rejection:evidence", "asset_id": missing}
        )
    with pytest.raises(ValueError, match=match) as error:
        cases_from_jsonl(text([value]), snapshot, universe, source="review.jsonl")
    assert "review.jsonl:line=1: case=urn:toy:case:1" in str(error.value)


@pytest.mark.parametrize("mutation", ["unknown_attribute", "wrong_value", "missing_metadata"])
def test_without_original_evidence_metadata_content_is_still_checked(mutation):
    from bindofell.benchmark.io import cases_from_jsonl

    snapshot, universe, value = original_evidence_inputs()
    data = snapshot.model_dump(mode="json")
    for asset in data["fields"]:
        asset["evidence"] = []
        if mutation == "missing_metadata":
            asset["description"] = None
    from bindofell.domain.models import EstateSnapshot

    snapshot = EstateSnapshot.model_validate(data)
    if mutation == "unknown_attribute":
        value["gold"]["evidence"][0]["attribute"] = "invented_attribute"
    elif mutation == "wrong_value":
        value["gold"]["evidence"][0]["value"] = "Invented source meaning"
    with pytest.raises(ValueError, match="metadata"):
        cases_from_jsonl(text([value]), snapshot, universe)


def test_existing_records_cannot_be_bypassed_by_minting_a_new_evidence_id():
    from bindofell.benchmark.io import cases_from_jsonl

    snapshot, universe, value = original_evidence_inputs()
    source = value["gold"]["evidence"][0]
    source["evidence_id"] = "urn:toy:brand:new"
    source["value"] = "Invented source meaning"
    with pytest.raises(ValueError, match="original evidence"):
        cases_from_jsonl(text([value]), snapshot, universe)


def test_original_evidence_can_be_referenced_or_excerpted_with_a_new_id():
    from bindofell.benchmark.io import cases_from_jsonl

    snapshot, universe, value = original_evidence_inputs()
    source = value["gold"]["evidence"][0]
    source["evidence_id"] = "urn:toy:excerpt:1"
    source["value"] = "authored for tests only."
    assert cases_from_jsonl(text([value]), snapshot, universe)
    source["evidence_id"] = "urn:toy:evidence:0"
    with pytest.raises(ValueError, match="original evidence"):
        cases_from_jsonl(text([value]), snapshot, universe)


def test_independent_decisions_are_context_validated_and_roundtrip_without_erasing_disagreement():
    from copy import deepcopy

    from bindofell.benchmark.io import cases_from_jsonl, cases_to_jsonl

    from .test_models import mapping_review_payload

    snapshot, universe, original = original_evidence_inputs()
    value = mapping_review_payload()
    value["gold"] = deepcopy(original["gold"])
    value["adjudication"]["mapping"] = deepcopy(value["gold"])
    for annotation, accepted in zip(
        value["annotations"], value["gold"]["accepted_field_ids"], strict=True
    ):
        annotation["mapping"] = deepcopy(value["gold"])
        annotation["mapping"]["accepted_field_ids"] = [accepted]
    cases = cases_from_jsonl(text([value]), snapshot, universe)
    restored = cases_from_jsonl(cases_to_jsonl(cases), snapshot, universe)
    assert restored[0].annotations[0].mapping.accepted_field_ids != (
        restored[0].annotations[1].mapping.accepted_field_ids
    )
    value["annotations"][0]["mapping"]["evidence"][0]["source_digest"] = "b" * 64
    with pytest.raises(ValueError, match="annotation.*digest"):
        cases_from_jsonl(text([value]), snapshot, universe)
