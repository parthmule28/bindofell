"""Strict offline JSONL, canonical hashes and frozen eligibility validation."""

import hashlib
import json
import math
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Literal, NoReturn, Self, cast

from pydantic import Field, model_validator

from bindofell.benchmark.models import EvaluationCase, unique_sorted
from bindofell.domain.models import Attributes, Contract, EstateSnapshot, Identifier, Text


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


def validate_case(
    case: EvaluationCase,
    snapshot: EstateSnapshot,
    universe: EligibleUniverse,
) -> None:
    if case.snapshot_id != snapshot.snapshot_id:
        raise ValueError(f"case {case.case_id}: wrong snapshot {case.snapshot_id}")
    targets = set((*case.gold.accepted_field_ids, *case.gold.plausible_field_ids))
    absent = targets - {f.field_id for f in snapshot.fields}
    ineligible = targets - set(universe.field_ids)
    if absent:
        raise ValueError(f"case {case.case_id}: gold fields outside snapshot: {sorted(absent)}")
    if ineligible:
        raise ValueError(f"case {case.case_id}: ineligible gold fields: {sorted(ineligible)}")


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
