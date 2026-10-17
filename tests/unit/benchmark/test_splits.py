import json
from pathlib import Path

import pytest

from bindofell.benchmark.io import load_cases, make_universe
from bindofell.benchmark.models import EvaluationCase
from bindofell.metadata.loader import load_snapshot

FIXTURES = Path(__file__).parents[2] / "fixtures" / "benchmark"


def cases(count=18):
    snapshot = load_snapshot(FIXTURES / "toy_estate.json")
    originals = load_cases(FIXTURES / "toy_cases.jsonl", snapshot, make_universe(snapshot))
    result = []
    for i in range(count):
        value = originals[i % 3].model_dump(mode="json")
        value.update(case_id=f"urn:toy:case:{i:03}", split_group_id=f"urn:toy:group:{i // 2}")
        value["family_links"] = [{"kind": "paraphrase", "family_id": f"urn:toy:family:{i // 2}"}]
        result.append(EvaluationCase.model_validate(value))
    return tuple(result)


def test_split_is_deterministic_order_independent_and_seeded():
    from bindofell.benchmark.splits import assign_splits, manifest_to_json

    fixture = cases(60)
    one = assign_splits(fixture, seed=19)
    assert one == assign_splits(reversed(fixture), seed=19)
    assert manifest_to_json(one) == manifest_to_json(assign_splits(fixture, seed=19))
    assert one != assign_splits(fixture, seed=20)
    assert one.algorithm_version == "bindofell.grouped-stratified-greedy/1"
    assert one.seed == 19
    assert sum(c.case_count for c in one.counts) == len(fixture)
    assert sum(c.group_count for c in one.counts) == 30
    assert {a.partition for a in one.assignments} == {"train", "validation", "test"}
    for group in {c.split_group_id for c in fixture}:
        assert len({a.partition for a in one.assignments if a.split_group_id == group}) == 1
    for summary in one.counts:
        assert summary.case_count == (
            summary.direct_count + summary.no_match_count + summary.needs_clarification_count
        )
        assert (
            min(summary.direct_count, summary.no_match_count, summary.needs_clarification_count) > 0
        )


def test_tiny_corpora_preserve_groups_over_target_ratios():
    from bindofell.benchmark.splits import assign_splits

    result = assign_splits(cases(2), seed=1)
    assert len({a.partition for a in result.assignments}) == 1
    assert sum(c.case_count for c in result.counts) == 2
    assert sum(c.case_count == 0 for c in result.counts) == 2
    assert not assign_splits((), seed=1).assignments


@pytest.mark.parametrize("kind", ["concept", "paraphrase", "seed", "template", "related_target"])
def test_declared_family_cannot_span_groups(kind):
    from bindofell.benchmark.splits import assign_splits

    fixture = list(cases(4))
    a, b = fixture[0].model_dump(mode="json"), fixture[3].model_dump(mode="json")
    for v in (a, b):
        v["family_links"] = [{"kind": kind, "family_id": "urn:toy:shared"}]
    fixture[0], fixture[3] = EvaluationCase.model_validate(a), EvaluationCase.model_validate(b)
    with pytest.raises(ValueError, match="family.*urn:toy:shared.*group"):
        assign_splits(fixture, seed=1)


def test_manifest_roundtrip_and_validation_on_reload():
    from bindofell.benchmark.splits import assign_splits, manifest_from_json, manifest_to_json

    fixture = cases()
    manifest = assign_splits(fixture, seed=1)
    data = manifest_to_json(manifest)
    assert manifest_from_json(data, fixture) == manifest
    for mutation in ("overlap", "split_group", "counts", "digest", "algorithm", "missing", "extra"):
        value = json.loads(data)
        if mutation == "overlap":
            value["assignments"].append(value["assignments"][0])
        elif mutation == "split_group":
            value["assignments"][0]["partition"] = (
                "train" if value["assignments"][0]["partition"] != "train" else "test"
            )
        elif mutation == "counts":
            value["counts"][0]["case_count"] += 1
        elif mutation == "digest":
            value["cases_digest"] = "b" * 64
        elif mutation == "algorithm":
            value["algorithm_version"] = "unsupported"
        elif mutation == "missing":
            value["assignments"].pop()
        else:
            value["undocumented"] = True
        with pytest.raises(ValueError):
            manifest_from_json(json.dumps(value), fixture)
    with pytest.raises(ValueError, match="duplicate JSON key"):
        manifest_from_json(data.replace('"seed":', '"seed":1,"seed":'), fixture)


def test_manifest_reload_requires_explicit_algorithm_version():
    from bindofell.benchmark.splits import assign_splits, manifest_from_json, manifest_to_json

    fixture = cases()
    value = json.loads(manifest_to_json(assign_splits(fixture, seed=17)))
    del value["algorithm_version"]
    with pytest.raises(ValueError, match="algorithm_version"):
        manifest_from_json(json.dumps(value), fixture)
