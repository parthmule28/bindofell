from pathlib import Path

import pytest
from pydantic import ValidationError

from bindofell.benchmark.io import load_cases, make_universe
from bindofell.domain.models import BindingCandidate, field_id
from bindofell.metadata.loader import load_snapshot

FIXTURES = Path(__file__).parents[2] / "fixtures" / "benchmark"


def inputs():
    estate = load_snapshot(FIXTURES / "toy_estate.json")
    universe = make_universe(estate)
    return estate, universe, load_cases(FIXTURES / "toy_cases.jsonl", estate, universe)


def ranking(case, ids, scores=None):
    from bindofell.evaluation.contracts import CaseRanking

    return CaseRanking(
        schema_version="1.0",
        case_id=case.case_id,
        snapshot_id=case.snapshot_id,
        candidates=tuple(
            BindingCandidate(
                requirement_id=case.requirement.requirement_id,
                snapshot_id=case.snapshot_id,
                field_id=i,
                rank=n,
                raw_score=float(scores[n - 1] if scores else 10 - n),
                method_id="toy-supplied/1",
                evidence=case.gold.evidence[:1],
            )
            for n, i in enumerate(ids, 1)
        ),
    )


@pytest.mark.parametrize(
    "rank,top1,recall,mrr",
    [
        (1, 1, 1, 1),
        (2, 0, 1, 0.5),
        (5, 0, 1, 0.2),
        (6, 0, 0, 1 / 6),
        (None, 0, 0, 0),
        (0, 0, 0, 0),
    ],
)
def test_hand_calculated_ranks_or_alternatives_and_empty(rank, top1, recall, mrr):
    from bindofell.evaluation.metrics import ranking_metrics

    estate, universe, cases = inputs()
    case = cases[0]
    target = case.gold.accepted_field_ids[1]  # second OR alternative is equally valid
    distractors = [
        f.field_id for f in estate.fields if f.field_id not in case.gold.accepted_field_ids
    ]
    ids = [] if rank == 0 else distractors
    if rank:
        ids.insert(rank - 1, target)
    result = ranking_metrics((case,), (ranking(case, ids),), universe)
    assert result.support == 1
    assert result.top1 == top1
    assert result.recall_at_5 == recall
    assert result.mrr == pytest.approx(mrr)
    assert result.top1_hits == top1
    assert result.recall5_hits == recall
    assert result.reciprocal_rank_sum == pytest.approx(mrr)


def test_multi_case_denominator_and_same_column_wrong_table():
    from bindofell.benchmark.models import EvaluationCase
    from bindofell.evaluation.metrics import ranking_metrics

    _, universe, cases = inputs()
    value = cases[0].model_dump(mode="json")
    value["gold"]["accepted_field_ids"] = [field_id("toy", "Alpha", "key")]
    first = EvaluationCase.model_validate(value)
    value["case_id"] = "urn:toy:case:other"
    second = EvaluationCase.model_validate(value)
    result = ranking_metrics(
        (first, second),
        (
            ranking(first, [field_id("toy", "Beta", "key")]),
            ranking(second, [field_id("toy", "Alpha", "key")]),
        ),
        universe,
    )
    assert result.support == 2
    assert result.top1 == result.recall_at_5 == result.mrr == 0.5


def test_ties_use_canonical_field_id_and_reassign_ranks():
    _, universe, cases = inputs()
    case = cases[0]
    ids = list(reversed(universe.field_ids))
    ordered = ranking(case, ids, [0.0] * len(ids))
    assert tuple(c.field_id for c in ordered.candidates) == universe.field_ids
    assert tuple(c.rank for c in ordered.candidates) == tuple(range(1, len(ids) + 1))
    assert all(c.raw_score == 0.0 for c in ordered.candidates)


@pytest.mark.parametrize(
    "mutation", ["duplicate_field", "duplicate_rank", "gap", "nan", "snapshot"]
)
def test_rankings_reject_invalid_inputs(mutation):
    _, universe, cases = inputs()
    value = ranking(cases[0], universe.field_ids[:2]).model_dump(mode="json")
    if mutation == "duplicate_field":
        value["candidates"][1]["field_id"] = value["candidates"][0]["field_id"]
    elif mutation == "duplicate_rank":
        value["candidates"][1]["rank"] = 1
    elif mutation == "gap":
        value["candidates"][1]["rank"] = 3
    elif mutation == "nan":
        value["candidates"][1]["raw_score"] = float("nan")
    else:
        value["candidates"][1]["snapshot_id"] = "urn:toy:other"
    from bindofell.evaluation.contracts import CaseRanking

    with pytest.raises(ValidationError):
        CaseRanking.model_validate(value)


def test_empty_direct_support_null_and_ineligible_gold_not_a_miss():
    from bindofell.evaluation.metrics import coverage_audit, ranking_metrics

    estate, universe, cases = inputs()
    result = ranking_metrics(cases[1:], [ranking(c, []) for c in cases[1:]], universe)
    assert result.support == 0
    assert result.top1 is result.recall_at_5 is result.mrr is None
    assert coverage_audit(cases[1:], estate, universe).coverage is None
    reduced = make_universe(
        estate,
        field_ids=(cases[0].gold.accepted_field_ids[0],),
        rule_id="urn:toy:eligibility:subset",
    )
    audit = coverage_audit(cases, estate, reduced)
    assert audit.support == audit.covered_cases == 1
    assert audit.coverage == 1.0  # any eligible OR alternative, plus separate full integrity audit
    assert audit.issues[0].case_id == cases[0].case_id
    assert audit.issues[0].ineligible_field_ids == (cases[0].gold.accepted_field_ids[1],)
    with pytest.raises(ValueError, match="ineligible"):
        ranking_metrics(cases[:1], (ranking(cases[0], []),), reduced)


def rule():
    from bindofell.evaluation.contracts import OutcomeRule

    return OutcomeRule(
        rule_id="urn:toy:rule:explicit",
        version="1",
        config={"fixture": True},
        input_features=("synthetic human-supplied decisions",),
        description="No classifier; deliberately supplied test predictions",
    )


def decision(case, prediction):
    from bindofell.evaluation.contracts import OutcomeDecision

    return OutcomeDecision(
        schema_version="1.0",
        case_id=case.case_id,
        snapshot_id=case.snapshot_id,
        rule_id=rule().rule_id,
        rule_version="1",
        prediction=prediction,
        rationale="Synthetic test decision",
        input_reference="synthetic://test",
    )


def test_three_by_three_confusion_counts_both_other_classes():
    from bindofell.benchmark.models import EvaluationCase
    from bindofell.evaluation.metrics import classification_metrics

    _, _, originals = inputs()
    cases, predictions = [], []
    for original in originals:
        for p, predicted in enumerate(("DIRECT", "NO_MATCH", "NEEDS_CLARIFICATION")):
            value = original.model_dump(mode="json")
            value["case_id"] += f":{p}"
            case = EvaluationCase.model_validate(value)
            cases.append(case)
            predictions.append(decision(case, predicted))
    report = classification_metrics(cases, rule=rule(), decisions=predictions)
    assert report.status == "evaluated"
    assert report.support == 9
    assert all((r.direct, r.no_match, r.needs_clarification) == (1, 1, 1) for r in report.confusion)
    for metric in report.classes:
        assert (metric.tp, metric.fp, metric.fn, metric.support) == (1, 2, 2, 3)
        assert metric.precision == metric.recall == metric.f1 == pytest.approx(1 / 3)


@pytest.mark.parametrize(
    "truth,predicted,tp,fp,fn,precision,recall,f1",
    [
        (None, None, 0, 0, 0, None, None, None),
        ("direct", "DIRECT", 0, 0, 0, None, None, None),
        ("no_match", "DIRECT", 0, 0, 1, None, 0, 0),
        ("direct", "NO_MATCH", 0, 1, 0, 0, None, 0),
        ("no_match", "NO_MATCH", 1, 0, 0, 1, 1, 1),
    ],
)
def test_zero_denominators_and_raw_counts(truth, predicted, tp, fp, fn, precision, recall, f1):
    from bindofell.evaluation.metrics import classification_metrics

    _, _, cases = inputs()
    chosen = [c for c in cases if c.task_label == truth]
    result = classification_metrics(
        chosen, rule=rule(), decisions=[decision(c, predicted) for c in chosen]
    )
    no_match = next(m for m in result.classes if m.label == "NO_MATCH")
    assert (no_match.tp, no_match.fp, no_match.fn) == (tp, fp, fn)
    assert (no_match.precision, no_match.recall, no_match.f1) == (precision, recall, f1)


def test_absent_rule_means_not_evaluated_and_complete_decisions_required():
    from bindofell.evaluation.metrics import classification_metrics

    _, _, cases = inputs()
    assert classification_metrics(cases).status == "not_evaluated"
    with pytest.raises(ValueError, match="rule"):
        classification_metrics(cases, decisions=(decision(cases[0], "NO_MATCH"),))
    with pytest.raises(ValueError, match="every"):
        classification_metrics(cases, rule=rule(), decisions=())
    all_decisions = [decision(c, "DIRECT") for c in cases]
    with pytest.raises(ValueError, match="duplicate"):
        classification_metrics(cases, rule=rule(), decisions=all_decisions + all_decisions[:1])


def test_coverage_rejects_snapshot_mismatch_and_duplicate_case_ids():
    from bindofell.evaluation.metrics import coverage_audit

    estate, universe, cases = inputs()
    wrong_snapshot = cases[0].model_copy(update={"snapshot_id": "urn:toy:other"})
    with pytest.raises(ValueError, match="snapshot"):
        coverage_audit((wrong_snapshot,), estate, universe)
    with pytest.raises(ValueError, match="duplicate"):
        coverage_audit((cases[0], cases[0]), estate, universe)
