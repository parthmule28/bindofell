from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from bindofell.benchmark.io import load_cases, make_universe
from bindofell.benchmark.splits import assign_splits
from bindofell.evaluation.contracts import CaseRanking
from bindofell.evaluation.runner import evaluate_supplied
from bindofell.metadata.loader import load_snapshot
from bindofell.retrieval.lexical import LexicalIndex

FIXTURES = Path(__file__).parents[2] / "fixtures/benchmark"


def evaluation(top_k=None):
    estate = load_snapshot(FIXTURES / "toy_estate.json")
    universe = make_universe(estate)
    cases = load_cases(FIXTURES / "toy_cases.jsonl", estate, universe)
    index = LexicalIndex(estate, universe, profile="field_descriptions")
    ranks = [
        CaseRanking(
            schema_version="1.0",
            case_id=c.case_id,
            snapshot_id=c.snapshot_id,
            candidates=index.search(
                c.requirement.text, requirement_id=c.requirement.requirement_id, top_k=top_k
            ),
        )
        for c in cases
    ]
    result = evaluate_supplied(
        estate,
        cases,
        universe,
        ranks,
        method=index.method,
        split_manifest=assign_splits(cases, seed=17),
    )
    return index, result


def manifest(tmp_path, seconds=(1.0, 2.0, 3.0), host=None):
    from bindofell.experiments.manifest import CaseLatency, build_manifest

    index, result = evaluation()
    lock = tmp_path / "uv.lock"
    lock.write_bytes(b"synthetic lock bytes\n")
    return build_manifest(
        result,
        index,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        index_seconds=0.25,
        query_latencies=tuple(
            CaseLatency(case_id=c.case.case_id, seconds=s)
            for c, s in zip(result.results, seconds, strict=True)
        ),
        git_root=tmp_path,
        lock_path=lock,
        host=host or {"machine": "toy"},
    )


def test_manifest_records_hashes_config_grade_and_unavailable_provenance(tmp_path):
    from bindofell.benchmark.io import content_digest

    result = manifest(tmp_path)
    static = result.static
    assert static.provenance.annotation_grade == "provisional_curator"
    assert static.provenance.universe_digest == static.provenance.universe.digest
    assert static.lock_sha256 == content_digest("synthetic lock bytes\n")
    assert static.git.status == "unavailable" and static.git.revision is None
    assert static.research.status == "unavailable" and static.research.digest is None
    assert static.document_count == 8
    assert static.tokenizer_id == "bindofell.nfkc-casefold-words/1"
    assert static.provenance.method.config["package_version"] == "0.3.13"
    assert static.ranking_depth == "full-universe" and static.mrr_label == "MRR"
    assert (
        len(static.documents_digest)
        == len(static.tokens_digest)
        == len(static.results_digest)
        == 64
    )
    assert result.observations.median_seconds == 2.0
    assert result.observations.p95_seconds == 3.0
    assert result.observations.percentile_definition == "nearest-rank ceil(0.95*n)"


def test_static_projection_excludes_timing_timestamp_host_and_incidental_paths(tmp_path):
    from bindofell.experiments.manifest import (
        manifest_from_json,
        manifest_to_json,
        static_projection,
    )

    one = manifest(tmp_path, seconds=(1.0, 2.0, 3.0), host={"machine": "one"})
    other_path = tmp_path / "different-output-location"
    other_path.mkdir()
    two = manifest(other_path, seconds=(5.0, 8.0, 9.0), host={"machine": "other"})
    changed = two.observations.model_copy(update={"started_at": datetime(2026, 2, 1, tzinfo=UTC)})
    two = two.model_copy(update={"observations": changed})
    assert static_projection(one) == static_projection(two)
    assert one.static_digest == two.static_digest
    assert manifest_to_json(one) != manifest_to_json(two)
    assert manifest_from_json(manifest_to_json(one)) == one


@pytest.mark.parametrize("seconds", [-1.0, float("nan"), float("inf")])
def test_invalid_measured_times_fail(seconds):
    from bindofell.experiments.manifest import CaseLatency

    with pytest.raises(ValidationError):
        CaseLatency(case_id="urn:toy:case", seconds=seconds)


def test_git_and_missing_lock_are_explicitly_available_or_unavailable(tmp_path):
    from bindofell.experiments.manifest import capture_git, lock_digest

    assert capture_git(None).status == "unavailable"
    assert lock_digest(tmp_path / "missing.lock") is None
    repository = Path(__file__).parents[3]
    assert capture_git(repository).status == "available"
    assert len(capture_git(repository).revision) == 40


def test_manifest_cannot_label_a_truncated_ranking_as_unrestricted_mrr(tmp_path):
    from bindofell.experiments.manifest import CaseLatency, build_manifest

    index, result = evaluation(top_k=1)
    assert all(len(r.ranking.candidates) == 1 for r in result.results)
    with pytest.raises(ValueError, match="full.*ranking"):
        build_manifest(
            result,
            index,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            index_seconds=0.1,
            query_latencies=tuple(
                CaseLatency(case_id=c.case.case_id, seconds=0.1) for c in result.results
            ),
            git_root=None,
            lock_path=None,
        )


def test_manifest_timestamp_requires_an_explicit_timezone():
    from bindofell.experiments.manifest import CaseLatency, build_manifest

    index, result = evaluation()
    with pytest.raises(ValueError, match="timezone"):
        build_manifest(
            result,
            index,
            started_at=datetime(2026, 1, 1),
            index_seconds=0.1,
            query_latencies=tuple(
                CaseLatency(case_id=c.case.case_id, seconds=0.1) for c in result.results
            ),
            git_root=None,
            lock_path=None,
        )


@pytest.mark.parametrize("partial", [{"revision": "a" * 40}, {"dirty": False}])
def test_unavailable_git_never_carries_partial_guessed_values(partial):
    from bindofell.experiments.manifest import GitState

    with pytest.raises(ValidationError, match="Git"):
        GitState(status="unavailable", **partial)


def test_artifact_publication_rejects_a_report_from_another_ranking(tmp_path):
    from bindofell.experiments.run import write_experiment

    run = manifest(tmp_path)
    _, truncated = evaluation(top_k=1)
    output = tmp_path / "mismatch"
    with pytest.raises(ValueError, match="manifest.*result"):
        write_experiment(output, truncated, run)
    assert not output.exists()


def test_publication_io_failure_cleans_only_its_new_artifacts(tmp_path, monkeypatch):
    import os

    from bindofell.experiments.run import write_experiment

    run = manifest(tmp_path)
    _, result = evaluation()
    real_link = os.link

    def fail_on_second_file(source, destination):
        if Path(destination).name == "cases.jsonl":
            raise OSError("synthetic disk error")
        return real_link(source, destination)

    monkeypatch.setattr(os, "link", fail_on_second_file)
    output = tmp_path / "failed"
    with pytest.raises(OSError, match="synthetic disk error"):
        write_experiment(output, result, run)
    assert not output.exists()
    assert not list(tmp_path.glob(".failed.*"))
