"""Strict JSON snapshot I/O; no network or source metadata inference."""

import json
from pathlib import Path
from typing import NoReturn, cast

from pydantic import ValidationError

from bindofell.domain.models import EstateSnapshot


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON value: {value}")


def snapshot_from_json(text: str, *, source: str = "<string>") -> EstateSnapshot:
    try:
        value = json.loads(text, object_pairs_hook=_object, parse_constant=_nonfinite)
        if (
            isinstance(value, dict)
            and cast(dict[str, object], value).get("schema_version") != "1.0"
        ):
            raise ValueError("unsupported schema_version (expected 1.0)")
        return EstateSnapshot.model_validate(value)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"{source}: invalid snapshot: {exc}") from exc


def snapshot_to_json(snapshot: EstateSnapshot) -> str:
    return (
        json.dumps(
            snapshot.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )


def load_snapshot(path: str | Path) -> EstateSnapshot:
    path = Path(path)
    try:
        return snapshot_from_json(path.read_text(encoding="utf-8"), source=str(path))
    except UnicodeError as exc:
        raise ValueError(f"{path}: invalid snapshot encoding: {exc}") from exc


def write_snapshot(snapshot: EstateSnapshot, path: str | Path) -> None:
    Path(path).write_text(snapshot_to_json(snapshot), encoding="utf-8")
