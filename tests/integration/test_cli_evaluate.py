import json

import pytest

from bindofell.benchmark.io import canonical_json
from bindofell.evaluation.contracts import EvaluationResult
from bindofell.experiments.manifest import manifest_from_json, static_projection

from .test_cli_search import FIXTURES, cli


def arguments(cases=None):
    return [
        "evaluate",
        "--estate",
        FIXTURES / "toy_estate.json",
        "--cases",
        cases or FIXTURES / "toy_cases.jsonl",
        "--split",
        "all",
        "--profile",
        "names",
    ]


def test_evaluate_preserves_b02_metrics_full_rankings_and_reproducible_artifacts(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    for out in (first, second):
        result = cli(*arguments(), "--seed", "17", "--output-dir", out)
        assert result.returncode == 0, result.stderr
    assert {p.name for p in first.iterdir()} == {
        "metrics.json",
        "cases.jsonl",
        "run.json",
        "split.json",
        "universe.json",
    }
    report = EvaluationResult.model_validate_json((first / "metrics.json").read_text())
    assert report.direct.support == 1
    assert (
        report.direct.top1 == 0.0 and report.direct.recall_at_5 == 1.0 and report.direct.mrr == 0.5
    )
    assert report.classification.status == "not_evaluated"
    from bindofell.benchmark.io import load_cases, make_universe
    from bindofell.evaluation.runner import evaluate_supplied
    from bindofell.metadata.loader import load_snapshot

    snapshot = load_snapshot(FIXTURES / "toy_estate.json")
    universe = make_universe(snapshot)
    authoritative = evaluate_supplied(
        snapshot,
        load_cases(FIXTURES / "toy_cases.jsonl", snapshot, universe),
        universe,
        [r.ranking for r in report.results],
        method=report.provenance.method,
        split_manifest=report.provenance.split_manifest,
    )
    assert authoritative == report
    assert len(report.results) == 3
    assert all(len(r.ranking.candidates) == 8 for r in report.results)
    assert all(r.outcome is None for r in report.results)
    assert (first / "cases.jsonl").read_bytes() == (second / "cases.jsonl").read_bytes()
    assert (first / "metrics.json").read_bytes() == (second / "metrics.json").read_bytes()
    one = manifest_from_json((first / "run.json").read_text())
    two = manifest_from_json((second / "run.json").read_text())
    assert static_projection(one) == static_projection(two)
    assert one.static.provenance == report.provenance
    assert one.static.exploratory and one.static.split_origin == "generated"
    assert one.static.ranking_depth == "full-universe"
    assert len(one.observations.queries) == 3
    for name in ("metrics.json", "run.json", "split.json", "universe.json"):
        text = (first / name).read_text()
        assert text == canonical_json(json.loads(text))


def test_frozen_manifest_replay_and_selected_partition(tmp_path):
    exploratory = tmp_path / "exploratory"
    assert cli(*arguments(), "--seed", "17", "--output-dir", exploratory).returncode == 0
    out = tmp_path / "frozen"
    result = cli(
        *arguments(),
        "--split",
        "train",
        "--split-manifest",
        exploratory / "split.json",
        "--output-dir",
        out,
    )
    assert result.returncode == 0, result.stderr
    report = EvaluationResult.model_validate_json((out / "metrics.json").read_text())
    manifest = manifest_from_json((out / "run.json").read_text())
    assert manifest.static.provenance.partition == "train"
    assert manifest.static.split_origin == "frozen" and not manifest.static.exploratory
    selected = {
        a.case_id
        for a in manifest.static.provenance.split_manifest.assignments
        if a.partition == "train"
    }
    assert set(report.included_case_ids) == selected
    for record in report.results:
        assert record.ranking.snapshot_id == report.provenance.snapshot_id
        assert record.ranking.candidates[0].method_config == report.provenance.method.config


def test_rank_six_uses_full_mrr_and_changes_to_gold_never_change_retrieval(tmp_path):
    values = [json.loads(line) for line in (FIXTURES / "toy_cases.jsonl").read_text().splitlines()]
    first = tmp_path / "baseline"
    assert cli(*arguments(), "--seed", "17", "--output-dir", first).returncode == 0
    values[0]["gold"]["accepted_field_ids"] = [
        "urn:bindofell:field:toy/catalog=/schema=/table=Beta/column=key"
    ]
    changed = tmp_path / "changed.jsonl"
    changed.write_text("".join(json.dumps(v) + "\n" for v in values))
    second = tmp_path / "changed"
    result = cli(*arguments(changed), "--seed", "17", "--output-dir", second)
    assert result.returncode == 0, result.stderr
    before = EvaluationResult.model_validate_json((first / "metrics.json").read_text())
    after = EvaluationResult.model_validate_json((second / "metrics.json").read_text())
    assert after.results[0].first_matching_rank == 6
    assert after.direct.mrr == pytest.approx(1 / 6) and after.direct.recall_at_5 == 0.0
    assert tuple(r.ranking for r in before.results) == tuple(r.ranking for r in after.results)


@pytest.mark.parametrize(
    "mutation", ["snapshot", "gold", "schema", "unresolved", "grade", "evidence"]
)
def test_invalid_benchmark_fails_before_any_success_artifacts(tmp_path, mutation):
    values = [json.loads(line) for line in (FIXTURES / "toy_cases.jsonl").read_text().splitlines()]
    if mutation == "snapshot":
        values[0]["snapshot_id"] = "urn:toy:wrong"
    elif mutation == "gold":
        original = values[0]["gold"]["accepted_field_ids"][0]
        values[0] = json.loads(json.dumps(values[0]).replace(original, "urn:toy:missing"))
    elif mutation == "schema":
        values[0]["schema_version"] = "unsupported"
    elif mutation == "unresolved":
        values[0]["review_state"] = "unresolved"
    elif mutation == "grade":
        values[0]["annotation_grade"] = "expert_verified"
    else:
        values[0]["gold"]["evidence"][0]["source_digest"] = "b" * 64
    cases = tmp_path / "invalid.jsonl"
    cases.write_text("".join(json.dumps(v) + "\n" for v in values))
    out = tmp_path / "not-created"
    result = cli(*arguments(cases), "--seed", "17", "--output-dir", out)
    assert result.returncode != 0 and result.stderr
    assert not out.exists()
    assert not list(tmp_path.glob(".not-created.*"))


def test_zero_direct_support_missing_split_policy_and_no_overwrite(tmp_path):
    cases = tmp_path / "bc.jsonl"
    cases.write_text("\n".join((FIXTURES / "toy_cases.jsonl").read_text().splitlines()[1:]) + "\n")
    out = tmp_path / "bc"
    assert cli(*arguments(cases), "--output-dir", out).returncode != 0
    assert not out.exists()
    result = cli(*arguments(cases), "--seed", "17", "--output-dir", out)
    assert result.returncode == 0, result.stderr
    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["direct"]["support"] == 0
    assert metrics["direct"]["mrr"] is metrics["direct"]["recall_at_5"] is None
    assert metrics["classification"]["status"] == "not_evaluated"
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    assert cli(*arguments(cases), "--seed", "17", "--output-dir", out).returncode != 0
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}


def test_mixed_valid_annotation_grades_are_rejected_without_artifacts(tmp_path):
    from copy import deepcopy

    values = [json.loads(line) for line in (FIXTURES / "toy_cases.jsonl").read_text().splitlines()]
    case = values[0]
    case["schema_version"] = "1.1"
    case["annotation_grade"] = "independently_validated"
    original = deepcopy(case["annotations"][0])
    case["annotations"] = []
    for person in ("one", "two"):
        annotation = deepcopy(original)
        annotation["annotator"].update(person_id=f"urn:synthetic:reviewer:{person}", name=person)
        annotation.update(independent=True, mapping=deepcopy(case["gold"]))
        case["annotations"].append(annotation)
    adjudicator = deepcopy(original["annotator"])
    adjudicator.update(person_id="urn:synthetic:reviewer:three", name="three")
    case["adjudication"] = {
        "adjudicator": adjudicator,
        "task_label": "direct",
        "signed_off": True,
        "rationale": "Synthetic gate test only",
        "mapping": deepcopy(case["gold"]),
    }
    path = tmp_path / "mixed.jsonl"
    path.write_text("".join(json.dumps(v) + "\n" for v in values))
    output = tmp_path / "not-created"
    result = cli(*arguments(path), "--seed", "17", "--output-dir", output)
    assert result.returncode != 0 and "grades" in result.stderr
    assert not output.exists()
