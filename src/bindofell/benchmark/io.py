"""Strict offline JSONL, canonical hashes and frozen eligibility validation."""

import hashlib
import json
import math
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Literal, NoReturn, Self, cast

from pydantic import Field, model_validator

from bindofell.benchmark.models import EvaluationCase, GroundTruthMapping, unique_sorted
from bindofell.domain.models import Attributes, Contract, EstateSnapshot, Evidence, Identifier, Text


def canonical_json(value: object) -> str:
    return (
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    )


def content_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON value: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        _nonfinite(value)
    return number


def strict_object(text: str, *, schema_versions: tuple[str, ...] = ("1.0",)) -> dict[str, object]:
    text.encode("utf-8", errors="strict")
    value: object = json.loads(
        text, object_pairs_hook=_object, parse_constant=_nonfinite, parse_float=_finite_float
    )
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    result = cast(dict[str, object], value)
    # Also reject lone surrogate escapes, including in nested string values/keys.
    canonical_json(result).encode("utf-8", errors="strict")
    if result.get("schema_version") not in schema_versions:
        raise ValueError(
            f"case={result.get('case_id', '<unknown>')}: "
            f"unsupported schema_version (expected {schema_versions})"
        )
    return result


def jsonl_objects(
    text: str, source: str, *, schema_versions: tuple[str, ...] = ("1.0",)
) -> Iterator[tuple[int, dict[str, object]]]:
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    for line, data in enumerate(lines, 1):
        try:
            if not data.strip():
                raise ValueError("blank JSONL record")
            yield line, strict_object(data, schema_versions=schema_versions)
        except ValueError as exc:
            raise ValueError(f"{source}:line={line}: {exc}") from exc


def read_utf8(path: str | Path) -> str:
    path = Path(path)
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        line = raw[: exc.start].count(b"\n") + 1 if isinstance(exc, UnicodeDecodeError) else 1
        raise ValueError(f"{path}:line={line}: invalid UTF-8: {exc}") from exc


class EligibleUniverse(Contract):
    schema_version: Literal["1.0"] = "1.0"
    snapshot_id: Identifier
    rule_id: Identifier
    rule_version: Text
    rule_config: Attributes = Field(default_factory=dict)
    field_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def identities(self) -> Self:
        object.__setattr__(self, "field_ids", unique_sorted(self.field_ids, "universe field ID"))
        return self

    @property
    def digest(self) -> str:
        return content_digest(canonical_json(self.model_dump(mode="json")))


def validate_universe(universe: EligibleUniverse, snapshot: EstateSnapshot) -> None:
    if universe.snapshot_id != snapshot.snapshot_id:
        raise ValueError("universe snapshot differs from loaded snapshot")
    all_fields = {f.field_id for f in snapshot.fields}
    unknown = set(universe.field_ids) - all_fields
    if unknown:
        raise ValueError(f"universe fields outside snapshot: {sorted(unknown)}")
    if (
        universe.rule_id == "urn:bindofell:eligibility:all-physical-fields"
        and set(universe.field_ids) != all_fields
    ):
        raise ValueError("all-physical-fields policy requires the complete snapshot field set")


def make_universe(
    snapshot: EstateSnapshot,
    *,
    field_ids: Iterable[str] | None = None,
    rule_id: str = "urn:bindofell:eligibility:all-physical-fields",
    rule_version: str = "1",
    rule_config: Attributes | None = None,
) -> EligibleUniverse:
    universe = EligibleUniverse(
        snapshot_id=snapshot.snapshot_id,
        rule_id=rule_id,
        rule_version=rule_version,
        rule_config=rule_config or {},
        field_ids=tuple(field_ids)
        if field_ids is not None
        else tuple(f.field_id for f in snapshot.fields),
    )
    validate_universe(universe, snapshot)
    return universe


def _source_value_matches(claim: object, original: object, *, allow_excerpt: bool) -> bool:
    if canonical_json(claim) == canonical_json(original):
        return True
    return (
        allow_excerpt
        and isinstance(claim, str)
        and isinstance(original, str)
        and bool(claim.strip())
        and claim in original
    )


def _validate_source_evidence(evidence: Evidence, snapshot: EstateSnapshot) -> None:
    assets: dict[str, Contract] = {
        snapshot.snapshot_id: snapshot,
        snapshot.dataset.dataset_id: snapshot.dataset,
        **{t.table_id: t for t in snapshot.tables},
        **{f.field_id: f for f in snapshot.fields},
        **{r.relationship_id: r for r in snapshot.relationships},
    }
    if evidence.asset_id not in assets:
        raise ValueError(f"source evidence {evidence.evidence_id}: unknown snapshot asset")
    if evidence.source_digest not in {d.sha256 for d in snapshot.source_digests}:
        raise ValueError(
            f"source evidence {evidence.evidence_id}: digest absent from snapshot sources"
        )
    originals = tuple(
        e
        for asset in (*snapshot.tables, *snapshot.fields, *snapshot.relationships)
        for e in asset.evidence
    )
    same_id = tuple(e for e in originals if e.evidence_id == evidence.evidence_id)
    serialized = canonical_json(evidence.model_dump(mode="json"))
    if same_id and any(canonical_json(e.model_dump(mode="json")) != serialized for e in same_id):
        raise ValueError(f"source evidence {evidence.evidence_id}: modified original evidence ID")
    attached = tuple(e for e in originals if e.asset_id == evidence.asset_id and e.kind == "source")
    if attached:
        matches = tuple(
            e
            for e in attached
            if (
                e.source_digest == evidence.source_digest
                and e.source_locator == evidence.source_locator
                and e.attribute == evidence.attribute
            )
        )
        if not any(
            _source_value_matches(evidence.value, e.value, allow_excerpt=not same_id)
            for e in matches
        ):
            raise ValueError(
                f"source evidence {evidence.evidence_id}: locator/attribute/value "
                "does not match original evidence"
            )
        return
    # Generic snapshots may have no attached originals. Verify actual metadata;
    # a manifest digest alone cannot ground a made-up attribute or source value.
    metadata = assets[evidence.asset_id].model_dump(mode="json")
    attributes = cast(dict[str, object], metadata.get("attributes", {}))
    if evidence.attribute in attributes:
        original = attributes[evidence.attribute]
    elif evidence.attribute in metadata:
        original = metadata[evidence.attribute]
    else:
        raise ValueError(
            f"source evidence {evidence.evidence_id}: unknown source metadata attribute"
        )
    if not isinstance(original, (str, int, float, bool, type(None))) or not _source_value_matches(
        evidence.value, original, allow_excerpt=True
    ):
        raise ValueError(
            f"source evidence {evidence.evidence_id}: value contradicts source metadata"
        )


def _validate_mapping(
    mapping: GroundTruthMapping,
    snapshot: EstateSnapshot,
    universe: EligibleUniverse,
) -> None:
    targets = set((*mapping.accepted_field_ids, *mapping.plausible_field_ids))
    fields = {f.field_id for f in snapshot.fields}
    rejected = {r.field_id for r in mapping.rejected_candidates}
    absent = (targets | rejected) - fields
    ineligible = targets - set(universe.field_ids)
    if absent:
        raise ValueError(f"gold fields outside snapshot: {sorted(absent)}")
    if ineligible:
        raise ValueError(f"ineligible gold fields: {sorted(ineligible)}")
    for evidence in mapping.evidence:
        if evidence.kind == "source":
            _validate_source_evidence(evidence, snapshot)


def validate_case(
    case: EvaluationCase,
    snapshot: EstateSnapshot,
    universe: EligibleUniverse,
) -> None:
    if case.snapshot_id != snapshot.snapshot_id:
        raise ValueError(f"case {case.case_id}: wrong snapshot {case.snapshot_id}")
    mappings = [("gold", case.gold)]
    mappings.extend(
        (f"annotation {a.annotator.person_id}", a.mapping)
        for a in case.annotations
        if a.mapping is not None
    )
    if case.adjudication is not None and case.adjudication.mapping is not None:
        mappings.append(("adjudication", case.adjudication.mapping))
    for label, mapping in mappings:
        try:
            _validate_mapping(mapping, snapshot, universe)
        except ValueError as exc:
            raise ValueError(f"case {case.case_id} {label}: {exc}") from exc


def validate_cases(
    cases: Iterable[EvaluationCase],
    snapshot: EstateSnapshot,
    universe: EligibleUniverse,
    *,
    require_resolved: bool = False,
) -> tuple[EvaluationCase, ...]:
    validate_universe(universe, snapshot)
    ordered = tuple(sorted(cases, key=lambda c: c.case_id))
    unique_sorted(tuple(c.case_id for c in ordered), "case ID")
    for case in ordered:
        validate_case(case, snapshot, universe)
        if require_resolved and not case.is_scorable:
            raise ValueError(f"unresolved case cannot be scored: {case.case_id}")
    return ordered


def cases_from_jsonl(
    text: str,
    snapshot: EstateSnapshot,
    universe: EligibleUniverse,
    *,
    source: str = "<string>",
) -> tuple[EvaluationCase, ...]:
    validate_universe(universe, snapshot)
    cases: list[EvaluationCase] = []
    seen: set[str] = set()
    for line, value in jsonl_objects(text, source, schema_versions=("1.0", "1.1")):
        case_id = value.get("case_id", "<unknown>")
        try:
            case = EvaluationCase.model_validate(value)
            if case.case_id in seen:
                raise ValueError("duplicate case ID")
            validate_case(case, snapshot, universe)
            seen.add(case.case_id)
            cases.append(case)
        except ValueError as exc:
            raise ValueError(f"{source}:line={line}: case={case_id}: {exc}") from exc
    return tuple(sorted(cases, key=lambda c: c.case_id))


def load_cases(
    path: str | Path,
    snapshot: EstateSnapshot,
    universe: EligibleUniverse,
) -> tuple[EvaluationCase, ...]:
    return cases_from_jsonl(read_utf8(path), snapshot, universe, source=str(path))


def cases_to_jsonl(cases: Iterable[EvaluationCase]) -> str:
    ordered = tuple(sorted(cases, key=lambda c: c.case_id))
    unique_sorted(tuple(c.case_id for c in ordered), "case ID")
    return "".join(canonical_json(c.model_dump(mode="json")) for c in ordered)


def cases_digest(cases: Iterable[EvaluationCase]) -> str:
    return content_digest(cases_to_jsonl(cases))
