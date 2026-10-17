from copy import deepcopy

import pytest
from pydantic import ValidationError

from bindofell.domain.models import field_id


def payload(label="direct"):
    ids = [field_id("toy", t, "key") for t in ("Alpha", "Beta")]
    gold = {
        "schema_version": "1.0",
        "gold_version": "toy-gold/1",
        "task_label": label,
        "accepted_field_ids": ids if label == "direct" else [],
        "plausible_field_ids": ids if label == "needs_clarification" else [],
        "rationale": "Synthetic explanation, independent of any rankings.",
        "scope": "All fields of the frozen toy universe" if label == "no_match" else None,
        "missing_dimension": "entity" if label == "needs_clarification" else None,
        "interpretations": [{"field_id": i, "rationale": f"Interpretation for {i}"} for i in ids]
        if label == "needs_clarification"
        else [],
        "evidence": [
            {
                "evidence_id": f"urn:toy:evidence:{n}",
                "kind": "source",
                "asset_id": i,
                "source_locator": f"synthetic://toy/fields/{n}",
                "source_digest": "a" * 64,
                "attribute": "description",
                "value": "Synthetic metadata",
            }
            for n, i in enumerate(ids)
        ],
        "rejected_candidates": [],
    }
    return {
        "schema_version": "1.0",
        "case_version": "toy-cases/1",
        "case_id": "urn:toy:case:1",
        "snapshot_id": "urn:toy:snapshot:1",
        "task_label": label,
        "requirement": {"requirement_id": "urn:toy:requirement:1", "text": "  Original wording  "},
        "split_group_id": "urn:toy:group:1",
        "family_links": [],
        "protocol_version": "toy-protocol/1",
        "annotation_grade": "provisional_curator",
        "review_state": "resolved",
        "author_id": "urn:toy:person:curator",
        "authoring_basis": "Deliberately synthetic engineering fixture; no expert verification.",
        "annotations": [
            {
                "annotator": person("curator"),
                "independent": False,
                "task_label": label,
                "rationale": "Synthetic decision",
                "annotation_reference": "synthetic://decision/1",
            }
        ],
        "adjudication": None,
        "gold": gold,
    }


def person(name):
    return {
        "person_id": f"urn:toy:person:{name}",
        "name": name,
        "qualifications": "Synthetic role, no qualification claim",
        "domain_experience": "None claimed",
    }


def validated_payload():
    value = payload()
    value["annotation_grade"] = "independently_validated"
    value["annotations"] = [
        {**value["annotations"][0], "annotator": person(n), "independent": True}
        for n in ("one", "two")
    ]
    value["adjudication"] = {
        "adjudicator": person("three"),
        "task_label": "direct",
        "signed_off": True,
        "rationale": "Synthetic review gate test, not a real review",
    }
    return value


@pytest.mark.parametrize("label", ["direct", "no_match", "needs_clarification"])
def test_case_requires_task_specific_gold_shape(label):
    from bindofell.benchmark.models import EvaluationCase

    value = payload(label)
    case = EvaluationCase.model_validate(value)
    assert case.requirement.text == "  Original wording  "
    assert case.gold.rationale == value["gold"]["rationale"]
    assert EvaluationCase.model_validate(case.model_dump()) == case
    bad = deepcopy(value)
    if label == "direct":
        bad["gold"]["accepted_field_ids"] = []
    elif label == "no_match":
        bad["gold"]["scope"] = None
    else:
        bad["gold"]["missing_dimension"] = None
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(bad)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicates",
        "one_plausible",
        "duplicate_plausible",
        "no_evidence",
        "no_target_evidence",
        "no_provenance",
        "mixed_gold",
        "wrong_label",
        "no_interpretations",
        "unreasoned_rejection",
        "unknown_field",
        "unsupported_version",
    ],
)
def test_rejects_incomplete_or_ambiguous_contracts(mutation):
    from bindofell.benchmark.models import EvaluationCase

    value = payload(
        "needs_clarification"
        if "plausible" in mutation or mutation == "no_interpretations"
        else "direct"
    )
    if mutation == "duplicates":
        value["gold"]["accepted_field_ids"] *= 2
    elif mutation == "one_plausible":
        value["gold"]["plausible_field_ids"] = value["gold"]["plausible_field_ids"][:1]
    elif mutation == "duplicate_plausible":
        value["gold"]["plausible_field_ids"] = [value["gold"]["plausible_field_ids"][0]] * 2
    elif mutation == "no_evidence":
        value["gold"]["evidence"] = []
    elif mutation == "no_target_evidence":
        value["gold"]["evidence"] = value["gold"]["evidence"][:1]
    elif mutation == "no_provenance":
        del value["authoring_basis"]
    elif mutation == "mixed_gold":
        value["gold"]["plausible_field_ids"] = value["gold"]["accepted_field_ids"]
    elif mutation == "wrong_label":
        value["task_label"] = "no_match"
    elif mutation == "no_interpretations":
        value["gold"]["interpretations"] = []
    elif mutation == "unreasoned_rejection":
        value["gold"]["rejected_candidates"] = [{"field_id": "urn:toy:wrong", "rationale": " "}]
    elif mutation == "unknown_field":
        value["confidence"] = 0.9
    else:
        value["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(value)


def test_accepted_alternatives_are_sorted_or_ids_and_frozen():
    from bindofell.benchmark.models import EvaluationCase

    value = payload()
    value["gold"]["accepted_field_ids"].reverse()
    case = EvaluationCase.model_validate(value)
    assert case.gold.accepted_field_ids == tuple(sorted(value["gold"]["accepted_field_ids"]))
    with pytest.raises(ValidationError):
        case.case_id = "urn:toy:other"


def test_validated_grade_requires_two_independent_annotations_and_distinct_adjudicator():
    from bindofell.benchmark.models import EvaluationCase

    value = validated_payload()
    assert EvaluationCase.model_validate(value).is_scorable
    for mutation in ("one", "same", "dependent", "adjudicator", "unsigned", "absent", "label"):
        bad = deepcopy(value)
        if mutation == "one":
            bad["annotations"] = bad["annotations"][:1]
        elif mutation == "same":
            bad["annotations"][1]["annotator"] = bad["annotations"][0]["annotator"]
        elif mutation == "dependent":
            bad["annotations"][0]["independent"] = False
        elif mutation == "adjudicator":
            bad["adjudication"]["adjudicator"] = bad["annotations"][0]["annotator"]
        elif mutation == "unsigned":
            bad["adjudication"]["signed_off"] = False
        elif mutation == "label":
            bad["adjudication"]["task_label"] = "no_match"
        else:
            bad["adjudication"] = None
        with pytest.raises(ValidationError):
            EvaluationCase.model_validate(bad)


def test_provisional_is_curator_resolution_and_unresolved_is_not_scorable():
    from bindofell.benchmark.models import EvaluationCase

    value = payload()
    value["review_state"] = "unresolved"
    assert not EvaluationCase.model_validate(value).is_scorable
    value["adjudication"] = validated_payload()["adjudication"]
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(value)
