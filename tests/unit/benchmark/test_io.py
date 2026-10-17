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
