import json
from pathlib import Path

import pytest

from bindofell.benchmark.io import load_cases, make_universe
from bindofell.benchmark.models import EvaluationCase
from bindofell.benchmark.splits import assign_splits
from bindofell.metadata.loader import load_snapshot

from .test_metrics import decision, ranking, rule

FIXTURES = Path(__file__).parents[2] / "fixtures" / "benchmark"


def inputs():
    from bindofell.evaluation.contracts import MethodSpec

    snapshot = load_snapshot(FIXTURES / "toy_estate.json")
    universe = make_universe(snapshot)
    cases = load_cases(FIXTURES / "toy_cases.jsonl", snapshot, universe)
    method = MethodSpec(
        method_id="toy-supplied/1",
        version="1",
        config={},
        indexed_field_ids=universe.field_ids,
        universe_digest=universe.digest,
    )
    return snapshot, universe, cases, method, assign_splits(cases, seed=17)


def evaluate(cases=None, rankings=None, **kwargs):
    from bindofell.evaluation.runner import evaluate_supplied

    snapshot, universe, originals, method, manifest = inputs()
    cases = cases if cases is not None else originals
    manifest = assign_splits(cases, seed=17)
    rankings = rankings if rankings is not None else [ranking(c, []) for c in cases]
    return evaluate_supplied(
        snapshot, cases, universe, rankings, method=method, split_manifest=manifest, **kwargs
    )


def test_runner_preserves_candidates_evidence_and_static_provenance():
    from bindofell.evaluation.runner import (
        case_results_to_jsonl,
        evaluate_supplied,
        load_rankings,
        result_to_json,
    )

    snapshot, universe, cases, method, manifest = inputs()
    rankings = load_rankings(FIXTURES / "toy_rankings.jsonl")
    report = evaluate_supplied(
        snapshot, cases, universe, rankings, method=method, split_manifest=manifest
    )
    again = evaluate_supplied(
        snapshot,
        reversed(cases),
        universe,
        reversed(rankings),
        method=method,
        split_manifest=manifest,
    )
    assert report == again
    assert result_to_json(report) == result_to_json(again)
    assert case_results_to_jsonl(report) == case_results_to_jsonl(again)
    assert report.direct.support == 1
    assert report.direct.top1 == report.direct.recall_at_5 == report.direct.mrr == 1.0
    assert report.classification.status == "not_evaluated"
    assert report.coverage.issues == ()
    assert report.provenance.annotation_grade == "provisional_curator"
    assert report.provenance.source_digests == snapshot.source_digests
    assert report.provenance.universe_digest == universe.digest
    assert report.provenance.universe == universe
    assert report.provenance.split_manifest == manifest
    assert report.provenance.method == method
    assert report.original_case_ids == report.included_case_ids == tuple(c.case_id for c in cases)
    assert not report.excluded_case_ids
    for record, supplied in zip(report.results, rankings, strict=True):
        assert record.ranking == supplied
        assert record.case.case_version == "toy-cases/1"
        assert record.case.gold.gold_version == "toy-gold/1"
        for predicted, original in zip(record.ranking.candidates, supplied.candidates, strict=True):
            assert predicted.raw_score == original.raw_score
            assert predicted.evidence == original.evidence
    assert sum(s.support for s in report.label_supports) == 3


def test_acquisition_timestamp_is_excluded_from_static_comparison():
    from datetime import UTC, datetime

    from bindofell.evaluation.runner import evaluate_supplied, result_to_json

    snapshot, universe, cases, method, manifest = inputs()
    ranks = [ranking(c, []) for c in cases]
    changed = snapshot.model_copy(
        update={
            "dataset": snapshot.dataset.model_copy(
                update={"retrieved_at": datetime(2026, 1, 1, tzinfo=UTC)}
            )
        }
    )
    one = evaluate_supplied(
        snapshot, cases, universe, ranks, method=method, split_manifest=manifest
    )
    two = evaluate_supplied(changed, cases, universe, ranks, method=method, split_manifest=manifest)
    assert result_to_json(one) == result_to_json(two)
    assert "retrieved_at" not in result_to_json(one)


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("wrong_snapshot", "snapshot"),
        ("wrong_requirement", "requirement"),
        ("ineligible_candidate", "ineligible"),
        ("missing_ranking", "every"),
        ("duplicate_ranking", "duplicate"),
        ("missing_index_field", "universe"),
        ("wrong_universe_digest", "digest"),
        ("method", "method"),
        ("method_config", "config"),
        ("gold", "ineligible"),
        ("clarification", "ineligible"),
        ("unresolved", "unresolved"),
        ("mixed_grade", "grades"),
        ("split_conflict", "family"),
        ("manifest", "digest"),
    ],
)
def test_preflight_rejects_invalid_metadata_and_predictions(mutation, match):
    from bindofell.evaluation.contracts import CaseRanking, MethodSpec
    from bindofell.evaluation.runner import evaluate_supplied

    snapshot, universe, cases, method, manifest = inputs()
    cases, rankings = list(cases), [ranking(c, [universe.field_ids[0]]) for c in cases]
    if mutation in (
        "wrong_snapshot",
        "wrong_requirement",
        "ineligible_candidate",
        "method",
        "method_config",
    ):
        value = rankings[0].model_dump(mode="json")
        if mutation == "wrong_snapshot":
            value["snapshot_id"] = value["candidates"][0]["snapshot_id"] = "urn:toy:wrong"
        elif mutation == "wrong_requirement":
            value["candidates"][0]["requirement_id"] = "urn:toy:other"
        elif mutation == "ineligible_candidate":
            value["candidates"][0]["field_id"] = "urn:toy:missing"
        elif mutation == "method":
            value["candidates"][0]["method_id"] = "wrong-method"
        else:
            value["candidates"][0]["method_config"] = {"wrong": True}
        rankings[0] = CaseRanking.model_validate(value)
    elif mutation == "missing_ranking":
        rankings.pop()
    elif mutation == "duplicate_ranking":
        rankings.append(rankings[0])
    elif mutation in ("missing_index_field", "wrong_universe_digest"):
        value = method.model_dump(mode="json")
        if mutation == "missing_index_field":
            value["indexed_field_ids"].pop()
        else:
            value["universe_digest"] = "b" * 64
        method = MethodSpec.model_validate(value)
    elif mutation in ("gold", "clarification"):
        universe = make_universe(
            snapshot, field_ids=universe.field_ids[:1], rule_id="urn:toy:eligibility:subset"
        )
        method = MethodSpec(
            method_id=method.method_id,
            version="1",
            config={},
            indexed_field_ids=universe.field_ids,
            universe_digest=universe.digest,
        )
        if mutation == "clarification":
            cases, rankings = cases[1:], rankings[1:]
            manifest = assign_splits(cases, seed=17)
    elif mutation in ("unresolved", "mixed_grade", "split_conflict"):
        value = cases[0].model_dump(mode="json")
        if mutation == "unresolved":
            value["review_state"] = "unresolved"
        elif mutation == "mixed_grade":
            value["annotation_grade"] = "independently_validated"
            one = value["annotations"][0]
            value["annotations"] = []
            for suffix in ("one", "two"):
                actor = {**one["annotator"], "person_id": "urn:toy:person:" + suffix}
                value["annotations"].append({**one, "annotator": actor, "independent": True})
            value["adjudication"] = {
                "adjudicator": {**one["annotator"], "person_id": "urn:toy:person:third"},
                "signed_off": True,
                "task_label": "direct",
                "rationale": "Synthetic gate test",
            }
        else:
            value["family_links"] = [{"kind": "template", "family_id": "urn:toy:shared"}]
            other = cases[1].model_dump(mode="json")
            other["family_links"] = value["family_links"]
            cases[1] = EvaluationCase.model_validate(other)
        cases[0] = EvaluationCase.model_validate(value)
        if mutation != "split_conflict":
            manifest = assign_splits(cases, seed=17)
    else:
        manifest = manifest.model_copy(update={"cases_digest": "b" * 64})
    with pytest.raises(ValueError, match=match):
        evaluate_supplied(
            snapshot, cases, universe, rankings, method=method, split_manifest=manifest
        )


def test_explicit_rule_and_partition_selection():
    from bindofell.evaluation.runner import evaluate_supplied

    snapshot, universe, cases, method, manifest = inputs()
    selected_partition = manifest.assignments[0].partition
    selected_ids = {a.case_id for a in manifest.assignments if a.partition == selected_partition}
    chosen = [c for c in cases if c.case_id in selected_ids]
    report = evaluate_supplied(
        snapshot,
        cases,
        universe,
        [ranking(c, []) for c in chosen],
        method=method,
        split_manifest=manifest,
        partition=selected_partition,
        rule=rule(),
        decisions=[decision(c, "NO_MATCH") for c in chosen],
    )
    assert report.classification.status == "evaluated"
    assert report.classification.support == len(chosen)
    assert report.included_case_ids == tuple(c.case_id for c in chosen)
    assert all(r.outcome is not None for r in report.results)
    assert report.provenance.partition == selected_partition


@pytest.mark.parametrize(
    "data,match",
    [
        ('{"schema_version":"1.0","case_id":"urn:toy:1","case_id":"urn:toy:2"}', "duplicate"),
        ('{"schema_version":"1.0","raw_score":1e999}', "non-finite"),
        ('{"schema_version":"2.0"}', "schema_version"),
        ('{"schema_version":"1.0","unexpected":1}', "Extra inputs"),
    ],
)
def test_strict_ranking_jsonl_errors(data, match):
    from bindofell.evaluation.runner import rankings_from_jsonl

    with pytest.raises(ValueError, match=match) as exc:
        rankings_from_jsonl(data + "\n", source="rankings.jsonl")
    assert "rankings.jsonl:line=1" in str(exc.value)


def test_rankings_roundtrip_duplicate_cases_and_empty_evaluation():
    from bindofell.evaluation.runner import (
        load_rankings,
        rankings_from_jsonl,
        rankings_to_jsonl,
        result_to_json,
    )

    rankings = load_rankings(FIXTURES / "toy_rankings.jsonl")
    text = rankings_to_jsonl(reversed(rankings))
    assert rankings_from_jsonl(text) == rankings
    with pytest.raises(ValueError, match="duplicate"):
        rankings_from_jsonl(text + text)
    report = evaluate(cases=(), rankings=())
    value = json.loads(result_to_json(report))
    assert value["direct"]["support"] == 0
    assert value["direct"]["top1"] is None
    assert value["provenance"]["annotation_grade"] is None
