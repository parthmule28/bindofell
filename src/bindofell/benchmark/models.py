"""Sole owner of benchmark truth, annotation provenance and family contracts."""

from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, model_validator

from bindofell.domain.models import BusinessRequirement, Contract, Evidence, Identifier, Text

TaskLabel = Literal["direct", "no_match", "needs_clarification"]
TASK_LABELS: tuple[TaskLabel, ...] = ("direct", "no_match", "needs_clarification")
AnnotationGrade = Literal["provisional_curator", "independently_validated"]
ReviewState = Literal["unresolved", "resolved"]


def unique_sorted(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate {label}")
    return tuple(sorted(values))


class Contributor(Contract):
    person_id: Identifier
    name: Text
    qualifications: Text
    domain_experience: Text


class CandidateRationale(Contract):
    field_id: Identifier
    rationale: Text


class FamilyLink(Contract):
    kind: Literal["concept", "paraphrase", "seed", "template", "related_target"]
    family_id: Identifier


class GroundTruthMapping(Contract):
    schema_version: Literal["1.0"]
    gold_version: Text
    task_label: TaskLabel
    accepted_field_ids: tuple[Identifier, ...] = ()
    plausible_field_ids: tuple[Identifier, ...] = ()
    missing_dimension: Text | None = None
    scope: Text | None = None
    rationale: Text
    interpretations: tuple[CandidateRationale, ...] = ()
    rejected_candidates: tuple[CandidateRationale, ...] = ()
    evidence: Annotated[tuple[Evidence, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def shape(self) -> Self:
        accepted = unique_sorted(self.accepted_field_ids, "accepted field ID")
        plausible = unique_sorted(self.plausible_field_ids, "plausible field ID")
        if self.task_label == "direct":
            valid = bool(accepted) and not plausible and self.missing_dimension is None
        elif self.task_label == "no_match":
            valid = not accepted and not plausible and bool(self.scope)
            valid = valid and self.missing_dimension is None
        else:
            valid = not accepted and len(plausible) >= 2 and bool(self.missing_dimension)
        if not valid:
            raise ValueError(f"invalid {self.task_label} gold shape")
        interpreted = unique_sorted(
            tuple(c.field_id for c in self.interpretations), "interpretation"
        )
        if interpreted != plausible:
            raise ValueError("interpretations must describe every plausible field and no others")
        rejected = unique_sorted(tuple(c.field_id for c in self.rejected_candidates), "rejection")
        if set(rejected) & set((*accepted, *plausible)):
            raise ValueError("a target cannot also be rejected")
        source_assets = {e.asset_id for e in self.evidence if e.kind == "source"}
        if not source_assets or not set((*accepted, *plausible, *rejected)) <= source_assets:
            raise ValueError("source evidence required for every accepted/plausible/rejected field")
        unique_sorted(tuple(e.evidence_id for e in self.evidence), "evidence ID")
        object.__setattr__(self, "accepted_field_ids", accepted)
        object.__setattr__(self, "plausible_field_ids", plausible)
        for name in ("interpretations", "rejected_candidates"):
            object.__setattr__(
                self, name, tuple(sorted(getattr(self, name), key=lambda c: c.field_id))
            )
        object.__setattr__(
            self, "evidence", tuple(sorted(self.evidence, key=lambda e: e.evidence_id))
        )
        return self


class Annotation(Contract):
    annotator: Contributor
    independent: StrictBool
    task_label: TaskLabel
    rationale: Text
    annotation_reference: Text
    mapping: GroundTruthMapping | None = None

    @model_validator(mode="after")
    def decision_label(self) -> Self:
        if self.mapping is not None and self.task_label != self.mapping.task_label:
            raise ValueError("annotation label must match its mapping decision")
        return self


class Adjudication(Contract):
    adjudicator: Contributor
    task_label: TaskLabel
    signed_off: StrictBool
    rationale: Text
    mapping: GroundTruthMapping | None = None

    @model_validator(mode="after")
    def decision_label(self) -> Self:
        if self.mapping is not None and self.task_label != self.mapping.task_label:
            raise ValueError("adjudication label must match its mapping decision")
        return self


class EvaluationCase(Contract):
    schema_version: Literal["1.0", "1.1"]
    case_version: Text
    case_id: Identifier
    snapshot_id: Identifier
    requirement: BusinessRequirement
    task_label: TaskLabel
    split_group_id: Identifier
    family_links: tuple[FamilyLink, ...] = ()
    protocol_version: Text
    author_id: Identifier
    authoring_basis: Text
    annotation_grade: AnnotationGrade
    review_state: ReviewState
    annotations: Annotated[tuple[Annotation, ...], Field(min_length=1)]
    adjudication: Adjudication | None = None
    gold: GroundTruthMapping

    @property
    def is_scorable(self) -> bool:
        return self.review_state == "resolved"

    @model_validator(mode="after")
    def review(self) -> Self:
        if self.task_label != self.gold.task_label:
            raise ValueError("case and gold task labels must match")
        if self.annotation_grade == "independently_validated" and self.schema_version != "1.1":
            raise ValueError("independent mapping review requires case schema_version 1.1")
        if self.schema_version == "1.1" and any(a.mapping is None for a in self.annotations):
            raise ValueError("case 1.1 requires every annotator's complete mapping decision")
        people = unique_sorted(tuple(a.annotator.person_id for a in self.annotations), "annotator")
        if self.annotation_grade == "provisional_curator":
            if len(people) != 1 or self.adjudication is not None:
                raise ValueError("provisional_curator requires one curator and no adjudication")
            if self.annotations[0].independent:
                raise ValueError("solo curator resolution is not independent validation")
            if self.is_scorable and self.annotations[0].task_label != self.task_label:
                raise ValueError("curator resolution must match gold")
        else:
            if len(people) < 2 or not all(a.independent for a in self.annotations):
                raise ValueError("validated grade needs two distinct independent annotators")
            if self.is_scorable and (self.adjudication is None or not self.adjudication.signed_off):
                raise ValueError("resolved validated grade requires adjudicator sign-off")
        if self.adjudication is not None:
            if self.schema_version == "1.1" and self.adjudication.mapping is None:
                raise ValueError("case 1.1 requires the adjudicator's complete mapping decision")
            if self.is_scorable and self.adjudication.mapping != self.gold:
                raise ValueError("adjudication mapping must match the complete final gold mapping")
            if self.adjudication.adjudicator.person_id in people:
                raise ValueError("adjudicator must be distinct from annotators")
            if self.is_scorable and self.adjudication.task_label != self.task_label:
                raise ValueError("adjudicator decision must match resolved gold")
        links = [(f.kind, f.family_id) for f in self.family_links]
        if len(links) != len(set(links)):
            raise ValueError("duplicate family link")
        object.__setattr__(
            self,
            "family_links",
            tuple(sorted(self.family_links, key=lambda f: (f.kind, f.family_id))),
        )
        object.__setattr__(
            self,
            "annotations",
            tuple(sorted(self.annotations, key=lambda a: a.annotator.person_id)),
        )
        return self
