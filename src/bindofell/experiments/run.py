"""Thin offline composition: validated B01 documents -> BM25 -> authoritative B02 evaluation."""

import os
import tempfile
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from bindofell.benchmark.io import EligibleUniverse, canonical_json, content_digest, validate_cases
from bindofell.benchmark.models import EvaluationCase
from bindofell.benchmark.splits import Partition, SplitManifest, manifest_to_json, validate_manifest
from bindofell.domain.models import EstateSnapshot
from bindofell.evaluation.contracts import CaseRanking, EvaluationResult
from bindofell.evaluation.metrics import scoring_cases
from bindofell.evaluation.runner import case_results_to_jsonl, evaluate_supplied, result_to_json
from bindofell.experiments.manifest import (
    CaseLatency,
    RunManifest,
    SplitOrigin,
    build_manifest,
)
from bindofell.experiments.manifest import (
    manifest_to_json as run_to_json,
)
from bindofell.retrieval.documents import Profile
from bindofell.retrieval.lexical import LexicalIndex


def evaluate_experiment(
    snapshot: EstateSnapshot,
    cases: Iterable[EvaluationCase],
    universe: EligibleUniverse,
    *,
    profile: Profile,
    split_manifest: SplitManifest,
    partition: Partition | None,
    split_origin: SplitOrigin,
    git_root: Path | None = None,
    lock_path: Path | None = None,
) -> tuple[EvaluationResult, RunManifest]:
    started_at = datetime.now(UTC)
    all_cases = validate_cases(cases, snapshot, universe)
    validate_manifest(split_manifest, all_cases)
    if partition is not None and partition not in ("train", "validation", "test"):
        raise ValueError(f"unknown partition: {partition}")
    selected_ids = {
        a.case_id
        for a in split_manifest.assignments
        if partition is None or a.partition == partition
    }
    included = scoring_cases(c for c in all_cases if c.case_id in selected_ids)
    before_index = time.perf_counter()
    index = LexicalIndex(snapshot, universe, profile=profile)
    index_seconds = time.perf_counter() - before_index
    rankings: list[CaseRanking] = []
    latencies: list[CaseLatency] = []
    for case in included:
        before_query = time.perf_counter()
        # Only original request text and identity enter retrieval; no gold or review data.
        candidates = index.search(
            case.requirement.text, requirement_id=case.requirement.requirement_id, top_k=None
        )
        latencies.append(
            CaseLatency(case_id=case.case_id, seconds=time.perf_counter() - before_query)
        )
        rankings.append(
            CaseRanking(
                schema_version="1.0",
                case_id=case.case_id,
                snapshot_id=case.snapshot_id,
                candidates=candidates,
            )
        )
    result = evaluate_supplied(
        snapshot,
        all_cases,
        universe,
        rankings,
        method=index.method,
        split_manifest=split_manifest,
        partition=partition,
    )
    manifest = build_manifest(
        result,
        index,
        started_at=started_at,
        index_seconds=index_seconds,
        query_latencies=tuple(latencies),
        git_root=git_root,
        lock_path=lock_path,
        split_origin=split_origin,
    )
    return result, manifest


def write_experiment(output: Path, result: EvaluationResult, manifest: RunManifest) -> None:
    """Validate/serialize before writing; reserve a new directory and publish staged files.

    No existing directory is replaced. I/O failures remove only this writer's new
    files/directory, never unrelated contents. run.json is the last completion record.
    """
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"experiment output already exists: {output}")
    serialized_result = result_to_json(result)
    if (
        manifest.static.results_digest != content_digest(serialized_result)
        or manifest.static.provenance != result.provenance
    ):
        raise ValueError("manifest and evaluation result mismatch")
    artifacts = {
        "metrics.json": serialized_result,
        "cases.jsonl": case_results_to_jsonl(result),
        "split.json": manifest_to_json(result.provenance.split_manifest),
        "universe.json": canonical_json(result.provenance.universe.model_dump(mode="json")),
        "run.json": run_to_json(manifest),
    }
    with tempfile.TemporaryDirectory(prefix=f".{output.name}.", dir=output.parent) as staging:
        stage = Path(staging)
        for name, text in artifacts.items():
            (stage / name).write_text(text, encoding="utf-8")
        output.mkdir()  # Exclusive reservation; races cannot replace an existing directory.
        published: list[Path] = []
        try:
            for name in artifacts:
                destination = output / name
                os.link(stage / name, destination)
                published.append(destination)
        except OSError:
            for path in published:
                path.unlink()
            try:
                output.rmdir()
            except OSError:
                pass  # Preserve any unexpected external contents.
            raise
