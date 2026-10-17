"""Sole owner of ranking, outcome decision and metric result contracts."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from bindofell.benchmark.io import EligibleUniverse
from bindofell.benchmark.models import AnnotationGrade, EvaluationCase, TaskLabel, unique_sorted
from bindofell.benchmark.splits import Partition, SplitManifest
from bindofell.domain.models import (
    Attributes,
    BindingCandidate,
    Contract,
    Digest,
    Evidence,
    Identifier,
    SourceDigest,
    Text,
)

OutcomeLabel = Literal["DIRECT", "NO_MATCH", "NEEDS_CLARIFICATION"]
OUTCOME_LABELS: tuple[OutcomeLabel, ...] = ("DIRECT", "NO_MATCH", "NEEDS_CLARIFICATION")
Count = Annotated[int, Field(ge=0, strict=True)]
Rate = Annotated[float, Field(ge=0, le=1)]


class CaseRanking(Contract):
    schema_version: Literal["1.0"]
    case_id: Identifier
    snapshot_id: Identifier
    candidates: tuple[BindingCandidate, ...]

    @model_validator(mode="after")
    def integrity(self) -> Self:
        unique_sorted(tuple(c.field_id for c in self.candidates), "ranked field ID")
        ranks = [c.rank for c in self.candidates]
        if len(ranks) != len(set(ranks)):
            raise ValueError("duplicate candidate rank")
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise ValueError("candidate ranks must be contiguous starting at 1")
        if any(c.snapshot_id != self.snapshot_id for c in self.candidates):
            raise ValueError("candidate snapshot differs from ranking snapshot")
        ordered = sorted(self.candidates, key=lambda c: (-c.raw_score, c.field_id))
        object.__setattr__(
            self,
            "candidates",
            tuple(c.model_copy(update={"rank": rank}) for rank, c in enumerate(ordered, 1)),
        )
        return self


class OutcomeRule(Contract):
    rule_id: Identifier
    version: Text
    config: Attributes = Field(default_factory=dict)
    input_features: Annotated[tuple[Text, ...], Field(min_length=1)]
    description: Text


class OutcomeDecision(Contract):
    schema_version: Literal["1.0"]
    case_id: Identifier
    snapshot_id: Identifier
    rule_id: Identifier
    rule_version: Text
    prediction: OutcomeLabel
    rationale: Text
    input_reference: Text
    evidence: tuple[Evidence, ...] = ()


class DirectMetrics(Contract):
    support: Count
    top1_hits: Count
    recall5_hits: Count
    reciprocal_rank_sum: Annotated[float, Field(ge=0)]
    top1: Rate | None
    recall_at_5: Rate | None
    mrr: Rate | None


class CoverageIssue(Contract):
    case_id: Identifier
    missing_field_ids: tuple[Identifier, ...]
    ineligible_field_ids: tuple[Identifier, ...]


class CoverageAudit(Contract):
    support: Count
    covered_cases: Count
    coverage: Rate | None
    issues: tuple[CoverageIssue, ...]


class ClassMetrics(Contract):
    label: OutcomeLabel
    tp: Count
    fp: Count
    fn: Count
    support: Count
    precision: Rate | None
    recall: Rate | None
    f1: Rate | None


class ConfusionRow(Contract):
    truth: OutcomeLabel
    direct: Count
    no_match: Count
    needs_clarification: Count


class ClassificationMetrics(Contract):
    status: Literal["not_evaluated", "evaluated"]
    rule: OutcomeRule | None
    support: Count
    confusion: tuple[ConfusionRow, ...] = ()
    classes: tuple[ClassMetrics, ...] = ()


class MethodSpec(Contract):
    method_id: Text
    version: Text
    config: Attributes = Field(default_factory=dict)
    indexed_field_ids: tuple[Identifier, ...]
    universe_digest: Digest

    @model_validator(mode="after")
    def identities(self) -> Self:
        object.__setattr__(
            self, "indexed_field_ids", unique_sorted(self.indexed_field_ids, "indexed field ID")
        )
        return self


class LabelSupport(Contract):
    label: TaskLabel
    support: Count


class StaticProvenance(Contract):
    """Static B02 inputs only; B03 owns runtime observations and full run manifests."""

    schema_version: Literal["1.0"] = "1.0"
    snapshot_id: Identifier
    snapshot_digest: Digest
    source_digests: tuple[SourceDigest, ...]
    dataset_id: Identifier
    dataset_version: Text
    source_revision: Text
    universe: EligibleUniverse
    universe_digest: Digest
    cases_digest: Digest
    split_manifest: SplitManifest
    split_manifest_digest: Digest
    method: MethodSpec
    annotation_grade: AnnotationGrade | None
    partition: Partition | None


class CaseEvaluation(Contract):
    schema_version: Literal["1.0"] = "1.0"
    case: EvaluationCase
    ranking: CaseRanking
    first_matching_rank: Annotated[int, Field(gt=0, strict=True)] | None
    outcome: OutcomeDecision | None


class EvaluationResult(Contract):
    schema_version: Literal["1.0"] = "1.0"
    provenance: StaticProvenance
    original_case_ids: tuple[Identifier, ...]
    included_case_ids: tuple[Identifier, ...]
    excluded_case_ids: tuple[Identifier, ...] = ()
    label_supports: tuple[LabelSupport, ...]
    direct: DirectMetrics
    coverage: CoverageAudit
    classification: ClassificationMetrics
    results: tuple[CaseEvaluation, ...]
