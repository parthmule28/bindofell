"""Pure calculations; eligibility integrity is separate from retrieval misses."""

from collections import Counter
from collections.abc import Iterable
from math import fsum

from bindofell.benchmark.io import EligibleUniverse, validate_universe
from bindofell.benchmark.models import EvaluationCase, unique_sorted
from bindofell.domain.models import EstateSnapshot
from bindofell.evaluation.contracts import (
    OUTCOME_LABELS,
    CaseRanking,
    ClassificationMetrics,
    ClassMetrics,
    ConfusionRow,
    CoverageAudit,
    CoverageIssue,
    DirectMetrics,
    OutcomeDecision,
    OutcomeLabel,
    OutcomeRule,
)


def _ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def scoring_cases(cases: Iterable[EvaluationCase]) -> tuple[EvaluationCase, ...]:
    ordered = tuple(sorted(cases, key=lambda c: c.case_id))
    unique_sorted(tuple(c.case_id for c in ordered), "case ID")
    if any(not c.is_scorable for c in ordered):
        raise ValueError("unresolved cases cannot enter scoring")
    if len({c.annotation_grade for c in ordered}) > 1:
        raise ValueError("cannot mix annotation grades in one aggregate")
    return ordered


def validate_rankings(
    cases: tuple[EvaluationCase, ...],
    rankings: Iterable[CaseRanking],
    universe: EligibleUniverse,
) -> dict[str, CaseRanking]:
    supplied = tuple(rankings)
    unique_sorted(tuple(r.case_id for r in supplied), "ranking case ID")
    by_id = {r.case_id: r for r in supplied}
    if set(by_id) != {c.case_id for c in cases}:
        raise ValueError("supply exactly one ranking (possibly empty) for every included case")
    eligible = set(universe.field_ids)
    for case in cases:
        ranking = by_id[case.case_id]
        if ranking.snapshot_id != case.snapshot_id or case.snapshot_id != universe.snapshot_id:
            raise ValueError(f"wrong ranking snapshot for {case.case_id}")
        for candidate in ranking.candidates:
            if candidate.field_id not in eligible:
                raise ValueError(f"ineligible prediction for {case.case_id}: {candidate.field_id}")
            if candidate.requirement_id != case.requirement.requirement_id:
                raise ValueError(f"wrong candidate requirement for {case.case_id}")
    return by_id


def first_matching_rank(case: EvaluationCase, ranking: CaseRanking) -> int | None:
    return next(
        (c.rank for c in ranking.candidates if c.field_id in case.gold.accepted_field_ids), None
    )


def ranking_metrics(
    cases: Iterable[EvaluationCase],
    rankings: Iterable[CaseRanking],
    universe: EligibleUniverse,
) -> DirectMetrics:
    ordered = scoring_cases(cases)
    for case in ordered:
        targets = set((*case.gold.accepted_field_ids, *case.gold.plausible_field_ids))
        if not targets <= set(universe.field_ids):
            raise ValueError(f"ineligible gold in case {case.case_id}")
    by_id = validate_rankings(ordered, rankings, universe)
    ranks = [first_matching_rank(c, by_id[c.case_id]) for c in ordered if c.task_label == "direct"]
    support = len(ranks)
    top1 = sum(r == 1 for r in ranks)
    recall5 = sum(r is not None and r <= 5 for r in ranks)
    reciprocals = fsum(1 / r for r in ranks if r is not None)
    return DirectMetrics(
        support=support,
        top1_hits=top1,
        recall5_hits=recall5,
        reciprocal_rank_sum=reciprocals,
        top1=_ratio(top1, support),
        recall_at_5=_ratio(recall5, support),
        mrr=_ratio(reciprocals, support),
    )


def coverage_audit(
    cases: Iterable[EvaluationCase],
    snapshot: EstateSnapshot,
    universe: EligibleUniverse,
) -> CoverageAudit:
    """Audit all original A cases; any invalid alternative is an integrity issue."""
    validate_universe(universe, snapshot)
    ordered = tuple(sorted(cases, key=lambda c: c.case_id))
    unique_sorted(tuple(c.case_id for c in ordered), "coverage case ID")
    for case in ordered:
        if case.snapshot_id != snapshot.snapshot_id:
            raise ValueError(f"coverage case {case.case_id}: wrong snapshot {case.snapshot_id}")
    direct = tuple(c for c in ordered if c.task_label == "direct")
    present = {f.field_id for f in snapshot.fields}
    eligible = set(universe.field_ids)
    issues: list[CoverageIssue] = []
    covered = 0
    for case in direct:
        gold = set(case.gold.accepted_field_ids)
        missing, ineligible = gold - present, gold - eligible
        covered += bool(gold & present & eligible)
        if missing or ineligible:
            issues.append(
                CoverageIssue(
                    case_id=case.case_id,
                    missing_field_ids=tuple(sorted(missing)),
                    ineligible_field_ids=tuple(sorted(ineligible)),
                )
            )
    return CoverageAudit(
        support=len(direct),
        covered_cases=covered,
        coverage=_ratio(covered, len(direct)),
        issues=tuple(issues),
    )


def classification_metrics(
    cases: Iterable[EvaluationCase],
    *,
    rule: OutcomeRule | None = None,
    decisions: Iterable[OutcomeDecision] = (),
) -> ClassificationMetrics:
    ordered = scoring_cases(cases)
    predictions = tuple(decisions)
    if rule is None:
        if predictions:
            raise ValueError("outcome decisions require an explicit rule")
        return ClassificationMetrics(status="not_evaluated", rule=None, support=len(ordered))
    unique_sorted(tuple(d.case_id for d in predictions), "outcome case ID")
    by_id = {d.case_id: d for d in predictions}
    if set(by_id) != {c.case_id for c in ordered}:
        raise ValueError("rule must supply exactly one prediction for every included A/B/C case")
    label_map: dict[str, OutcomeLabel] = {
        "direct": "DIRECT",
        "no_match": "NO_MATCH",
        "needs_clarification": "NEEDS_CLARIFICATION",
    }
    matrix: Counter[tuple[OutcomeLabel, OutcomeLabel]] = Counter()
    for case in ordered:
        decision = by_id[case.case_id]
        if decision.snapshot_id != case.snapshot_id:
            raise ValueError(f"wrong outcome snapshot for {case.case_id}")
        if decision.rule_id != rule.rule_id or decision.rule_version != rule.version:
            raise ValueError(f"wrong outcome rule for {case.case_id}")
        matrix[label_map[case.task_label], decision.prediction] += 1
    rows: list[ConfusionRow] = []
    metrics: list[ClassMetrics] = []
    for label in OUTCOME_LABELS:
        rows.append(
            ConfusionRow(
                truth=label,
                direct=matrix[label, "DIRECT"],
                no_match=matrix[label, "NO_MATCH"],
                needs_clarification=matrix[label, "NEEDS_CLARIFICATION"],
            )
        )
        tp = matrix[label, label]
        fp = sum(matrix[truth, label] for truth in OUTCOME_LABELS if truth != label)
        fn = sum(matrix[label, prediction] for prediction in OUTCOME_LABELS if prediction != label)
        metrics.append(
            ClassMetrics(
                label=label,
                tp=tp,
                fp=fp,
                fn=fn,
                support=tp + fn,
                precision=_ratio(tp, tp + fp),
                recall=_ratio(tp, tp + fn),
                f1=_ratio(2 * tp, 2 * tp + fp + fn),
            )
        )
    return ClassificationMetrics(
        status="evaluated",
        rule=rule,
        support=len(ordered),
        confusion=tuple(rows),
        classes=tuple(metrics),
    )
