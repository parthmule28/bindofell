"""Versioned deterministic grouped stratification; declared families are indivisible."""

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Annotated, Literal

from pydantic import Field, StrictInt

from bindofell.benchmark.io import canonical_json, cases_digest, content_digest, strict_object
from bindofell.benchmark.models import TASK_LABELS, EvaluationCase, unique_sorted
from bindofell.domain.models import Contract, Digest, Identifier

Partition = Literal["train", "validation", "test"]
PARTITIONS: tuple[Partition, ...] = ("train", "validation", "test")
WEIGHTS = (0.6, 0.2, 0.2)
ALGORITHM = "bindofell.grouped-stratified-greedy/1"
Count = Annotated[int, Field(ge=0, strict=True)]


class SplitAssignment(Contract):
    case_id: Identifier
    split_group_id: Identifier
    partition: Partition


class PartitionCounts(Contract):
    partition: Partition
    group_count: Count
    case_count: Count
    direct_count: Count
    no_match_count: Count
    needs_clarification_count: Count


class SplitManifest(Contract):
    schema_version: Literal["1.0"] = "1.0"
    algorithm_version: Literal["bindofell.grouped-stratified-greedy/1"]
    seed: StrictInt
    cases_digest: Digest
    assignments: tuple[SplitAssignment, ...]
    counts: tuple[PartitionCounts, ...]


def validate_grouping(cases: Iterable[EvaluationCase]) -> tuple[EvaluationCase, ...]:
    ordered = tuple(sorted(cases, key=lambda c: c.case_id))
    unique_sorted(tuple(c.case_id for c in ordered), "case ID")
    families: dict[tuple[str, str], str] = {}
    for case in ordered:
        for link in case.family_links:
            key = (link.kind, link.family_id)
            if key in families and families[key] != case.split_group_id:
                raise ValueError(f"family {link.kind}:{link.family_id} crosses split groups")
            families[key] = case.split_group_id
    return ordered


def _counts(
    cases: tuple[EvaluationCase, ...], assignments: tuple[SplitAssignment, ...]
) -> tuple[PartitionCounts, ...]:
    by_id = {c.case_id: c for c in cases}
    result: list[PartitionCounts] = []
    for partition in PARTITIONS:
        selected = [a for a in assignments if a.partition == partition]
        labels = Counter(by_id[a.case_id].task_label for a in selected)
        result.append(
            PartitionCounts(
                partition=partition,
                group_count=len({a.split_group_id for a in selected}),
                case_count=len(selected),
                direct_count=labels["direct"],
                no_match_count=labels["no_match"],
                needs_clarification_count=labels["needs_clarification"],
            )
        )
    return tuple(result)


def assign_splits(cases: Iterable[EvaluationCase], *, seed: int) -> SplitManifest:
    """Greedy squared-error balance of per-class counts and total case counts.

    Place larger/rarer groups first, with seeded SHA-256 ordering for equal priorities.
    Preserve groups even when tiny inputs cannot achieve the target proportions.
    """
    ordered = validate_grouping(cases)
    groups: dict[str, list[EvaluationCase]] = defaultdict(list)
    for case in ordered:
        groups[case.split_group_id].append(case)
    totals = Counter(c.task_label for c in ordered)
    counts = {p: Counter[str]() for p in PARTITIONS}
    sizes = dict.fromkeys(PARTITIONS, 0)

    def priority(group: str) -> tuple[float, float, str]:
        members = groups[group]
        rarity = sum(1 / totals[c.task_label] for c in members)
        tie = content_digest(canonical_json([seed, group]))
        return -len(members), -rarity, tie

    assignments: list[SplitAssignment] = []
    for group in sorted(groups, key=priority):
        members = groups[group]
        labels = Counter(c.task_label for c in members)

        def cost(
            partition: Partition, labels: Counter[str] = labels, member_count: int = len(members)
        ) -> tuple[float, int]:
            index = PARTITIONS.index(partition)
            weight = WEIGHTS[index]
            # Marginal change in the global squared-error objective.
            delta = 0.0
            for label in TASK_LABELS:
                target = totals[label] * weight
                before = counts[partition][label] - target
                after = before + labels[label]
                delta += (after * after - before * before) / max(totals[label], 1)
            before_size = sizes[partition] - len(ordered) * weight
            after_size = before_size + member_count
            delta += (after_size**2 - before_size**2) / max(len(ordered), 1)
            return delta, index

        chosen = min(PARTITIONS, key=cost)
        counts[chosen].update(labels)
        sizes[chosen] += len(members)
        assignments.extend(
            SplitAssignment(case_id=c.case_id, split_group_id=group, partition=chosen)
            for c in members
        )
    final = tuple(sorted(assignments, key=lambda a: a.case_id))
    return SplitManifest(
        algorithm_version=ALGORITHM,
        seed=seed,
        cases_digest=cases_digest(ordered),
        assignments=final,
        counts=_counts(ordered, final),
    )


def validate_manifest(manifest: SplitManifest, cases: Iterable[EvaluationCase]) -> None:
    ordered = validate_grouping(cases)
    if manifest.cases_digest != cases_digest(ordered):
        raise ValueError("split manifest cases digest mismatch")
    unique_sorted(tuple(a.case_id for a in manifest.assignments), "split case ID")
    by_id = {c.case_id: c for c in ordered}
    if {a.case_id for a in manifest.assignments} != set(by_id):
        raise ValueError("split manifest must assign exactly the supplied cases")
    group_partitions: dict[str, Partition] = {}
    for assignment in manifest.assignments:
        group = by_id[assignment.case_id].split_group_id
        if assignment.split_group_id != group:
            raise ValueError(f"split group mismatch for {assignment.case_id}")
        if group in group_partitions and group_partitions[group] != assignment.partition:
            raise ValueError(f"split group {group} crosses partitions")
        group_partitions[group] = assignment.partition
    if manifest.counts != _counts(ordered, manifest.assignments):
        raise ValueError("split manifest counts differ from actual counts")
    replay = assign_splits(ordered, seed=manifest.seed)
    if replay.assignments != manifest.assignments:
        raise ValueError("split manifest differs from recorded algorithm/seed replay")


def manifest_to_json(manifest: SplitManifest) -> str:
    return canonical_json(manifest.model_dump(mode="json"))


def manifest_from_json(text: str, cases: Iterable[EvaluationCase]) -> SplitManifest:
    manifest = SplitManifest.model_validate(strict_object(text))
    validate_manifest(manifest, cases)
    return manifest
