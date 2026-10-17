"""OMOP 5.5 dictionary ingestion, retaining raw cells and source evidence."""

import csv
import hashlib
import io
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from bindofell.domain.models import (
    Dataset,
    EstateSnapshot,
    Evidence,
    FieldAddress,
    PhysicalField,
    Relationship,
    SourceDigest,
    Table,
    TableAddress,
)

OMOP_REVISION = "ba3dc1b651cc243279052bca3d051485c3ec1136"
ADAPTER_ID = "omop-cdm-5.5/v1"


def _rows(path: Path, raw: bytes, required: set[str]) -> list[tuple[int, dict[str, str]]]:
    line = 1
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        headers = next(reader, list[str]())
        if len(headers) != len(set(headers)):
            raise ValueError("duplicate headers")
        if any(not h.strip() for h in headers):
            raise ValueError("empty header")
        missing = required - set(headers)
        if missing:
            raise ValueError(f"missing required headers: {', '.join(sorted(missing))}")
        result: list[tuple[int, dict[str, str]]] = []
        while True:
            line = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                break
            if not row:
                continue
            if len(row) != len(headers):
                raise ValueError(f"column count {len(row)}; expected {len(headers)}")
            result.append((line, dict(zip(headers, row, strict=True))))
        return result
    except UnicodeError as exc:
        raise ValueError(f"{path}:row={line}: invalid encoding: {exc}") from exc
    except (ValueError, csv.Error) as exc:
        raise ValueError(f"{path}:row={line}: invalid CSV: {exc}") from exc


def _optional(value: str | None) -> str | None:
    return None if value is None or not value.strip() or value == "NA" else value


def _required(row: Mapping[str, str], name: str) -> str:
    value = _optional(row.get(name))
    if value is None:
        raise ValueError(f"{name} must not be missing")
    return value


def _flag(row: Mapping[str, str], name: str) -> bool | None:
    value = _optional(row.get(name))
    if value is None:
        return None
    if value.lower() not in ("true", "false"):
        raise ValueError(f"{name} must be true, false, blank or NA; got {value!r}")
    return value.lower() == "true"


def _evidence(
    path: Path, line: int, digest: str, asset: str, row: Mapping[str, str]
) -> tuple[Evidence, ...]:
    return tuple(
        Evidence(
            evidence_id=f"urn:bindofell:evidence:{digest}/{line}/{quote(key, safe='')}",
            kind="source",
            asset_id=asset,
            source_locator=f"{path.name}:row={line}:column={key}",
            source_digest=digest,
            attribute=key,
            value=value,
        )
        for key, value in sorted(row.items())
    )


def load_omop(
    table_path: str | Path,
    field_path: str | Path,
    *,
    namespace: str,
    source_revision: str,
    source_uri: str,
    expected_digests: Mapping[str, str] | None = None,
    retrieved_at: datetime | None = None,
    license: str | None = None,
) -> EstateSnapshot:
    """Import local files; provenance must explicitly distinguish fixtures from upstream."""
    table_path, field_path = Path(table_path), Path(field_path)
    if table_path.name == field_path.name:
        raise ValueError("table and field source filenames must be distinct")
    paths = (table_path, field_path)
    raw = {p.name: p.read_bytes() for p in paths}
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}
    if expected_digests is not None:
        if set(expected_digests) != set(hashes):
            raise ValueError("expected SHA-256 manifest must cover exactly both source filenames")
        for name, digest in hashes.items():
            if digest != expected_digests[name]:
                raise ValueError(
                    f"{name}: SHA-256 mismatch (expected {expected_digests[name]}, "
                    f"observed {digest})"
                )
    tables: dict[str, Table] = {}
    for line, row in _rows(table_path, raw[table_path.name], {"cdmTableName"}):
        try:
            name = _required(row, "cdmTableName")
            address = TableAddress(
                namespace=namespace, table=name, schema=_optional(row.get("schema"))
            )
            if name in tables:
                raise ValueError(f"duplicate table name {name!r}; field CSV cannot disambiguate it")
            tables[name] = Table(
                table_id=address.table_id,
                address=address,
                name=name,
                required=_flag(row, "isRequired"),
                description=_optional(row.get("tableDescription")),
                guidance=_optional(row.get("userGuidance")),
                etl_conventions=_optional(row.get("etlConventions")),
                attributes=row,
                evidence=_evidence(
                    table_path, line, hashes[table_path.name], address.table_id, row
                ),
            )
        except ValueError as exc:
            raise ValueError(f"{table_path}:row={line}: {exc}") from exc
    fields: dict[tuple[str, str], PhysicalField] = {}
    references: list[tuple[int, dict[str, str], PhysicalField]] = []
    for line, row in _rows(
        field_path, raw[field_path.name], {"cdmTableName", "cdmFieldName", "cdmDatatype"}
    ):
        try:
            table_name, name = _required(row, "cdmTableName"), _required(row, "cdmFieldName")
            if table_name not in tables:
                raise ValueError(f"unknown table {table_name!r}")
            table = tables[table_name]
            address = FieldAddress(
                namespace=namespace, table=table_name, column=name, schema=table.address.schema_name
            )
            if (table_name, name) in fields:
                raise ValueError(f"duplicate field {table_name}.{name}")
            field = PhysicalField(
                field_id=address.field_id,
                table_id=table.table_id,
                address=address,
                name=name,
                data_type=_optional(row.get("cdmDatatype")),
                required=_flag(row, "isRequired"),
                primary_key=_flag(row, "isPrimaryKey"),
                foreign_key=_flag(row, "isForeignKey"),
                guidance=_optional(row.get("userGuidance")),
                etl_conventions=_optional(row.get("etlConventions")),
                attributes=row,
                evidence=_evidence(
                    field_path, line, hashes[field_path.name], address.field_id, row
                ),
            )
            fields[table_name, name] = field
            if field.foreign_key:
                references.append((line, row, field))
        except ValueError as exc:
            raise ValueError(f"{field_path}:row={line}: {exc}") from exc
    relationships: list[Relationship] = []
    for line, row, source in references:
        try:
            target_table = _optional(row.get("fkTableName"))
            target_field = _optional(row.get("fkFieldName"))
            if target_table is None or target_field is None:
                raise ValueError("FK target table and field are required when isForeignKey=true")
            exact = fields.get((target_table, target_field))
            candidates = [
                f
                for (t, c), f in fields.items()
                if t.casefold() == target_table.casefold()
                and c.casefold() == target_field.casefold()
            ]
            if exact is not None:
                target = exact
            elif len(candidates) == 1:
                target = candidates[0]
            else:
                reason = "ambiguous FK" if candidates else "unresolved FK"
                raise ValueError(f"{reason} {target_table}.{target_field}")
            relationships.append(
                Relationship(
                    relationship_id=source.field_id + "/relationship=foreign_key",
                    source_field_ids=(source.field_id,),
                    target_field_ids=(target.field_id,),
                    kind="foreign_key",
                    evidence=tuple(
                        e
                        for e in source.evidence
                        if e.attribute in {"isForeignKey", "fkTableName", "fkFieldName"}
                    ),
                )
            )
        except ValueError as exc:
            raise ValueError(f"{field_path}:row={line}: {exc}") from exc
    identity = json.dumps(
        {
            "adapter": ADAPTER_ID,
            "namespace": namespace,
            "revision": source_revision,
            "digests": hashes,
        },
        sort_keys=True,
    )
    return EstateSnapshot(
        snapshot_id="urn:bindofell:snapshot:" + hashlib.sha256(identity.encode()).hexdigest(),
        dataset=Dataset(
            dataset_id="urn:bindofell:dataset:" + quote(namespace, safe=""),
            namespace=namespace,
            name="OMOP CDM metadata",
            version="5.5.0",
            revision=source_revision,
            source_uri=source_uri,
            license=license,
            retrieved_at=retrieved_at,
        ),
        source_digests=tuple(SourceDigest(path=k, sha256=v) for k, v in hashes.items()),
        tables=tuple(tables.values()),
        fields=tuple(fields.values()),
        relationships=tuple(relationships),
        adapter_id=ADAPTER_ID,
    )
