# B01 metadata contracts and ingestion

B01 implements the approved domain and metadata slice. `EvaluationCase` and
`GroundTruthMapping` are owned by [B02](b02-benchmark.md), which now provides
supplied-ranking evaluation. Ranking, model inference and search/evaluate
commands remain future work.

## Snapshot format and identity

`EstateSnapshot` uses `schema_version="1.0"`. It contains `snapshot_id`, a
`dataset` provenance record, `source_digests`, `tables`, `fields`, `relationships`
and optional `adapter_id`. See the runnable synthetic example at
[`tests/fixtures/estate-v1.json`](../../tests/fixtures/estate-v1.json).

Generate the complete JSON Schema from the canonical Pydantic models:

```sh
uv run python -c 'import json; from bindofell.domain.models import EstateSnapshot; print(json.dumps(EstateSnapshot.model_json_schema(), indent=2))'
```

`load_snapshot(path)`, `snapshot_from_json(text)`, `snapshot_to_json(snapshot)`
and `write_snapshot(snapshot, path)` are in `bindofell.metadata.loader`. JSON
uses UTF-8, sorted object keys, compact separators and a final newline. Arrays
of assets, relationships and source digests are canonically ordered. Unsupported
versions, duplicate JSON keys, non-finite values, unknown contract fields,
invalid IDs and dangling relationships fail validation with file/field context.
`write_snapshot` writes the specified path; retain versioned paths when keeping
historical snapshots.

Canonical addresses contain namespace, optional catalog/schema, table and
column. Every slot is explicit; missing catalog/schema uses an empty slot,
while explicitly supplied empty or surrounding-whitespace segments are rejected.
The remaining values use UTF-8 percent encoding, preserving source case:

```text
urn:bindofell:table:estate/catalog=/schema=x/table=T
urn:bindofell:field:estate/catalog=/schema=x/table=T/column=C
```

An absent catalog and schema `x` differ from catalog `x` and an absent schema.
Escaped slashes/percent signs cannot collapse into qualified-address separators.
`TableAddress` and `FieldAddress` expose the JSON key `schema` as Python
`schema_name` to avoid shadowing Pydantic's method. ID and parent-address
consistency are checked at construction, including for same-named tables in
different schemas. IDs do not incorporate snapshot versions and do not assert
unchanged semantics across source releases.

Contracts are frozen, collections are tuples, and attribute/config mappings
are copied into read-only mappings. Source extension maps currently support
typed scalar values; nested extension objects are rejected rather than dropped.
Optional metadata remains `None`. `DerivedBinding` is only an opaque reference
and input-field envelope: no parsing or execution of expressions is implemented.

## OMOP adapter

`bindofell.metadata.adapters.omop.load_omop(table_path, field_path, *, namespace,
source_revision, source_uri, expected_digests=None, retrieved_at=None, license=None)`
reads local files only. Explicit provenance arguments let synthetic inputs be
identified honestly. The adapter maps the 5.5 dictionary structure, not patient
data or business-binding annotations.

- Required headers are `cdmTableName` for tables and `cdmTableName`,
  `cdmFieldName`, `cdmDatatype` for fields. Optional headers/cells may be absent.
- Blank/whitespace-only cells and the OMOP `NA` sentinel map to `None` in
  optional interpreted properties; original cells, including unknown columns,
  remain in `attributes`. Names and descriptions are never guessed or renamed.
- `userGuidance` maps to guidance, `etlConventions` remains separate and table
  descriptions stay on tables. OMOP supplies no separate field-description
  column. `isRequired` is retained as requiredness; nullable is not invented.
- True/false key flags are interpreted case-insensitively; unknown flag values
  fail. Foreign-key targets must resolve. The upstream FK references are
  uppercase while asset names are lowercase: exact matching takes priority,
  then a unique case-insensitive lookup is allowed. Ambiguous/missing targets
  fail, preserving raw reference spellings as evidence.
- Field CSV rows identify tables by name only. Duplicate table names therefore
  fail in this adapter, even across schemas; the generic snapshot supports fully
  qualified same-named tables. No table schema is inferred for a field.
- Errors include the source file and physical starting row. Quoted multiline
  values, UTF-8/BOM and additive columns are supported; malformed rows, duplicate
  headers/assets, invalid encoding and incomplete relationships are rejected.

Source evidence includes file SHA-256, original cell, attribute and physical
row/column locator. The snapshot ID hashes adapter version, namespace, source
revision and both source-file digests. Acquisition time does not enter that ID.

## Local acquisition and real-source check

```sh
uv run python scripts/fetch_omop_metadata.py --output-dir .data/omop-v5.5.0
uv run python scripts/fetch_omop_metadata.py --output-dir .data/omop-v5.5.0 --verify-only
```

The first command requires network access and a new output directory. It checks
that `v5.5.0` resolves to `ba3dc1b651cc243279052bca3d051485c3ec1136`, downloads
from that full commit, verifies the reviewed hashes below, imports the CSVs and
writes source files, `snapshot.json` and `manifest.json`. It never overwrites an
existing acquisition. An interrupted write may leave an incomplete directory;
inspect it and choose a fresh path. The offline verifier checks the pinned files,
reimports them, compares snapshot bytes and checks manifest counts/identity.

| Pinned source file | SHA-256 |
|---|---|
| `OMOP_CDMv5.5_Table_Level.csv` | `42553b33bd7ec7085b0bc8df029fc6fd83aaa12650686bb259c4d492a10eb95d` |
| `OMOP_CDMv5.5_Field_Level.csv` | `7089ca523c13a29ec42ae55d4ef857a67bde0718a777c221858fad029b939994` |
| `DESCRIPTION` | `88a1f1f5ba02ecc694b327d3a989b3cb97ed1cb6c12092c84094ce49f95f7aed` |

The separate B01 import on 2026-10-17 observed **42 tables, 456 fields and 189
foreign-key relationships**. The local generated manifest records these counts,
source digests, adapter version, retrieval time and snapshot digest. It is not a
unit-test dependency or a claim of expert business-binding validation.

The package's [pinned DESCRIPTION](https://github.com/OHDSI/CommonDataModel/blob/ba3dc1b651cc243279052bca3d051485c3ec1136/DESCRIPTION)
declares Apache License 2.0. No upstream CSVs/descriptions are committed by this
work. Component notices and redistribution obligations still need checking
before bundling them; vocabulary/patient records are not acquired. The project's
50-paper research ledger remains unavailable and has not been reconstructed.

## Search documents and reproducibility

`build_search_documents(snapshot, profile=...)` constructs the same ordered field
IDs under every profile. Each named channel keeps source-evidence IDs; missing
selected channels are listed in `omitted_channels` and emit no placeholder.

| Profile | Selected channels, in text order |
|---|---|
| `names` | table name, field name |
| `field_descriptions` | preceding names, field description, field guidance |
| `table_context` | preceding channels, table description, table guidance |

ETL conventions, datatypes, keys and relationships stay structured in the
snapshot; they are not silently inserted into these profiles. `SearchDocument.text`
joins labeled channels without rewriting their values. `documents_to_jsonl`
sorts by field ID and writes canonical JSONL with serializer ID
`bindofell.search-document/1.0`, profile, channels, omissions and snapshot ID.

Repeated serialization of identical inputs is byte-stable. Across acquisitions,
compare source hashes, snapshot IDs and documents; retrieval timestamps are
observations. Full snapshot bytes include `dataset.retrieved_at`, so compare
their projection excluding that field when acquisition times differ. Manifest
snapshot hashes verify one particular stored acquisition, including its timestamp.

Unit tests block network connections. Real acquisition/import is an explicit
separate check. Pyright's Node runtime is locked through the `pyright[nodejs]`
development dependency. No `bindofell` executable is declared until its B03
implementation exists.
