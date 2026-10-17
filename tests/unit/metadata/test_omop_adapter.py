import csv
import hashlib

import pytest


def load(files, **kwargs):
    from bindofell.metadata.adapters.omop import load_omop

    return load_omop(
        *files,
        namespace="synthetic.omop",
        source_revision="synthetic-fixture",
        source_uri="synthetic://omop-shaped",
        **kwargs,
    )


def modify(path, change):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames
        rows = list(reader)
    change(rows)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, headers)
        writer.writeheader()
        writer.writerows(rows)


def test_adapter_preserves_source_metadata_missingness_and_fk_case(omop_files):
    estate = load(omop_files)
    fields = {(f.address.table, f.name): f for f in estate.fields}
    key = fields["entity", "id"]
    ref = fields["entity", "code_ref"]
    assert key.data_type == "integer" and key.primary_key is True
    assert key.description is None and key.guidance is None
    assert ref.required is None and ref.nullable is None
    assert ref.guidance == "Synthetic reference"
    assert key.attributes["extraSource"] == "field-extra"
    assert ref.attributes["fkTableName"] == "CODES"
    assert ref.address.schema_name == "demo"
    (relation,) = estate.relationships
    assert relation.source_field_ids == (ref.field_id,)
    assert relation.target_field_ids == (fields["codes", "id"].field_id,)
    assert all("field.csv:row=3:" in e.source_locator for e in relation.evidence)


def test_adapter_records_counts_hashes_and_stable_snapshot_identity(omop_files):
    from bindofell.metadata.loader import snapshot_to_json

    estate = load(omop_files)
    assert (len(estate.tables), len(estate.fields), len(estate.relationships)) == (2, 3, 1)
    assert {d.path: d.sha256 for d in estate.source_digests} == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in omop_files
    }
    assert snapshot_to_json(estate) == snapshot_to_json(load(omop_files))
    modify(omop_files[1], lambda rows: rows[0].update(userGuidance="New source words"))
    assert load(omop_files).snapshot_id != estate.snapshot_id


@pytest.mark.parametrize(
    "change,match",
    [
        (lambda rows: rows.append(rows[0].copy()), "duplicate field"),
        (lambda rows: rows[0].update(cdmFieldName=""), "cdmFieldName"),
        (lambda rows: rows[0].update(cdmTableName="missing"), "unknown table"),
        (lambda rows: rows[1].update(fkFieldName="missing"), "unresolved FK"),
        (lambda rows: rows[1].update(fkTableName="NA"), "FK target"),
        (lambda rows: rows[0].update(isRequired="maybe"), "isRequired"),
    ],
)
def test_adapter_errors_identify_file_and_source_row(omop_files, change, match):
    modify(omop_files[1], change)
    with pytest.raises(ValueError, match=match) as error:
        load(omop_files)
    assert "field.csv:row=" in str(error.value)


def test_optional_type_and_missing_flag_headers_are_not_inferred(omop_files):
    modify(omop_files[1], lambda rows: rows[0].update(cdmDatatype="", isPrimaryKey="NA"))
    estate = load(omop_files)
    key = next(f for f in estate.fields if f.address.table == "entity" and f.name == "id")
    assert key.data_type is None and key.primary_key is None
    assert key.attributes["isPrimaryKey"] == "NA"


@pytest.mark.parametrize(
    "content,match",
    [
        (b"cdmTableName,cdmFieldName\nx,y\n", "missing required headers.*cdmDatatype"),
        (b"cdmTableName,cdmFieldName,cdmDatatype\nx,y\n", "column count"),
        (b'cdmTableName,cdmFieldName,cdmDatatype\n"unterminated', "CSV"),
        (b"\xff", "encoding"),
        (b"cdmTableName,cdmFieldName,cdmDatatype,cdmDatatype\n", "duplicate headers"),
    ],
)
def test_adapter_rejects_malformed_csv(omop_files, content, match):
    omop_files[1].write_bytes(content)
    with pytest.raises(ValueError, match=match):
        load(omop_files)


def test_adapter_rejects_duplicate_tables_and_hash_mismatch(omop_files):
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load(omop_files, expected_digests={p.name: "0" * 64 for p in omop_files})
    modify(omop_files[0], lambda rows: rows.append(rows[0].copy()))
    with pytest.raises(ValueError, match="table.csv:row=4.*duplicate table"):
        load(omop_files)


def test_fk_casefold_lookup_rejects_ambiguous_reference(omop_files):
    def table_change(rows):
        rows.append({**rows[1], "cdmTableName": "CODES"})

    def field_change(rows):
        rows.append({**rows[2], "cdmTableName": "CODES"})
        rows[1]["fkTableName"] = "Codes"

    modify(omop_files[0], table_change)
    modify(omop_files[1], field_change)
    with pytest.raises(ValueError, match="ambiguous FK"):
        load(omop_files)


def test_multiline_csv_preserves_guidance_and_reports_physical_row(omop_files):
    modify(omop_files[1], lambda rows: rows[0].update(userGuidance="Line one\nLine two, continued"))
    estate = load(omop_files)
    key = next(f for f in estate.fields if f.address.table == "entity" and f.name == "id")
    assert key.guidance == "Line one\nLine two, continued"
    assert all("row=4:" in e.source_locator for e in estate.relationships[0].evidence)
