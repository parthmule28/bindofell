"""Offline evaluator for supplied rankings, with no retrieval or decision heuristics."""

from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from bindofell.benchmark.io import (
    EligibleUniverse,
    canonical_json,
    cases_digest,
    content_digest,
    jsonl_objects,
    read_utf8,
    validate_cases,
)
from bindofell.benchmark.models import TASK_LABELS, EvaluationCase, unique_sorted
from bindofell.benchmark.splits import (
    Partition,
    SplitManifest,
    manifest_to_json,
    validate_grouping,
    validate_manifest,
)
from bindofell.domain.models import EstateSnapshot
from bindofell.evaluation.contracts import (
    CaseEvaluation,
    CaseRanking,
    EvaluationResult,
    LabelSupport,
    MethodSpec,
    OutcomeDecision,
    OutcomeRule,
    StaticProvenance,
)
from bindofell.evaluation.metrics import (
    classification_metrics,
    coverage_audit,
    first_matching_rank,
    ranking_metrics,
    scoring_cases,
    validate_rankings,
)


def rankings_from_jsonl(text: str, *, source: str = "<string>") -> tuple[CaseRanking, ...]:
    rankings: list[CaseRanking] = []
    seen: set[str] = set()
    for line, value in jsonl_objects(text, source):
        case_id = value.get("case_id", "<unknown>")
        try:
            ranking = CaseRanking.model_validate(value)
            if ranking.case_id in seen:
                raise ValueError("duplicate ranking case ID")
            seen.add(ranking.case_id)
            rankings.append(ranking)
        except ValueError as exc:
            raise ValueError(f"{source}:line={line}: case={case_id}: {exc}") from exc
    return tuple(sorted(rankings, key=lambda r: r.case_id))


def load_rankings(path: str | Path) -> tuple[CaseRanking, ...]:
    return rankings_from_jsonl(read_utf8(path), source=str(path))


def rankings_to_jsonl(rankings: Iterable[CaseRanking]) -> str:
    ordered = tuple(sorted(rankings, key=lambda r: r.case_id))
    unique_sorted(tuple(r.case_id for r in ordered), "ranking case ID")
    return "".join(canonical_json(r.model_dump(mode="json")) for r in ordered)


def evaluate_supplied(
    snapshot: EstateSnapshot,
    cases: Iterable[EvaluationCase],
    universe: EligibleUniverse,
    rankings: Iterable[CaseRanking],
    *,
    method: MethodSpec,
    split_manifest: SplitManifest,
    partition: Partition | None = None,
    rule: OutcomeRule | None = None,
    decisions: Iterable[OutcomeDecision] = (),
) -> EvaluationResult:
    all_cases = validate_cases(cases, snapshot, universe)
    validate_grouping(all_cases)
    validate_manifest(split_manifest, all_cases)
    if partition is not None and partition not in ("train", "validation", "test"):
        raise ValueError(f"unknown partition: {partition}")
    selected_ids = {
        a.case_id
        for a in split_manifest.assignments
        if partition is None or a.partition == partition
    }
    included = scoring_cases(c for c in all_cases if c.case_id in selected_ids)
    if method.universe_digest != universe.digest:
        raise ValueError("method universe digest differs from frozen eligible universe")
    if method.indexed_field_ids != universe.field_ids:
        raise ValueError("method index must contain the complete eligible universe")
    supplied = tuple(rankings)
    by_id = validate_rankings(included, supplied, universe)
    for ranking in supplied:
        for candidate in ranking.candidates:
            if candidate.method_id != method.method_id:
                raise ValueError(f"candidate method mismatch in {ranking.case_id}")
            if candidate.method_config != method.config:
                raise ValueError(f"candidate method config mismatch in {ranking.case_id}")
    outcomes = tuple(decisions)
    classification = classification_metrics(included, rule=rule, decisions=outcomes)
    outcome_by_id = {d.case_id: d for d in outcomes}
    labels = Counter(c.task_label for c in included)
    provenance = StaticProvenance(
        snapshot_id=snapshot.snapshot_id,
        snapshot_digest=content_digest(
            canonical_json(snapshot.model_dump(mode="json", exclude={"dataset": {"retrieved_at"}}))
        ),
        source_digests=snapshot.source_digests,
        dataset_id=snapshot.dataset.dataset_id,
        dataset_version=snapshot.dataset.version,
        source_revision=snapshot.dataset.revision,
        universe=universe,
        universe_digest=universe.digest,
        cases_digest=cases_digest(all_cases),
        split_manifest=split_manifest,
        split_manifest_digest=content_digest(manifest_to_json(split_manifest)),
        method=method,
        annotation_grade=included[0].annotation_grade if included else None,
        partition=partition,
    )
    ids = tuple(c.case_id for c in included)
    return EvaluationResult(
        provenance=provenance,
        original_case_ids=ids,
        included_case_ids=ids,
        label_supports=tuple(
            LabelSupport(label=label, support=labels[label]) for label in TASK_LABELS
        ),
        direct=ranking_metrics(included, supplied, universe),
        coverage=coverage_audit(included, snapshot, universe),
        classification=classification,
        results=tuple(
            CaseEvaluation(
                case=case,
                ranking=by_id[case.case_id],
                first_matching_rank=first_matching_rank(case, by_id[case.case_id]),
                outcome=outcome_by_id.get(case.case_id),
            )
            for case in included
        ),
    )


def result_to_json(result: EvaluationResult) -> str:
    """The entire B02 result is static; it contains no latency or timestamps."""
    return canonical_json(result.model_dump(mode="json"))


def case_results_to_jsonl(result: EvaluationResult) -> str:
    return "".join(
        canonical_json(r.model_dump(mode="json"))
        for r in sorted(result.results, key=lambda r: r.case.case_id)
    )
