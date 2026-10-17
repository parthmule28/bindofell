# Bindofell Core Domain Contracts

**Status:** B00 proposal for review. These contracts describe the v0.1 retrieval boundary; they do not authorize B01 implementation.

## Scope and design rules

Bindofell v0.1 loads a versioned metadata estate, serializes selected metadata into deterministic retrieval documents, ranks physical fields for a business requirement, and records evidence and evaluation results. Source metadata remains intact and separate from retrieval text. A model score is a ranking signal, not a correctness probability.

The domain accepts any naming convention. It preserves source table and field labels as supplied and does not depend on class-word naming patterns, `snake_case`, or a preferred prefix.

## Identity and snapshot rules

- `DatasetId`, `TableId`, `FieldId`, `RelationshipId`, `RequirementId`, `BindingId`, `CaseId`, and `EvidenceId` are opaque, namespaced identifiers. Display labels are never identifiers.
- A field identity is formed from the source namespace and its complete qualified physical address: namespace, catalog (if present), schema (if present), table, and column. For example, an OMOP field could be represented as `urn:bindofell:field:ohdsi.omop.cdm/PERSON/person_id`. Each segment is encoded canonically and source case is preserved.
- Snapshot version and source file digest are recorded separately from the field address. This lets the same qualified field be compared across estate snapshots while still making every run reproducible. A rename or a distinct source namespace produces a distinct ID.
- IDs are stable within the selected namespace and address scheme; they do not claim that a field's meaning is unchanged across releases.

## Core types

These are conceptual contracts. Implement each in its single owning module below, with validated Python types and versioned serialization; consumers import the owner rather than redefine a contract.

| Owning module | Slice | Contracts |
|---|---|---|
| `src/bindofell/domain/models.py` | B01 | `BusinessRequirement`, `EstateSnapshot`, `Dataset`, `Table`, `PhysicalField`, `Relationship`, `Evidence`, `SemanticBinding`, `DirectBinding`, `BindingCandidate`, and the optional serialization-only `DerivedBinding` envelope |
| `src/bindofell/retrieval/documents.py` | B01 | `SearchDocument` and serializer profiles |
| `src/bindofell/benchmark/models.py` | B02 | `EvaluationCase`, `GroundTruthMapping`, case labels, annotation grade/review state and split-group identity |
| `src/bindofell/evaluation/contracts.py` | B02 | Per-case ranking results, optional outcome decisions and aggregate metric records |
| `src/bindofell/experiments/manifest.py` | B03 | Run manifest and runtime observations |

### `BusinessRequirement`

| Field | Meaning |
|---|---|
| `requirement_id` | Stable ID for a requirement within its source/benchmark namespace |
| `text` | User-authored natural-language statement |
| `business_context` | Optional domain, purpose or definition context supplied with the request |
| `constraints` | Optional explicit grain, entity, time role, population or other disambiguating requirements |
| `locale` | Optional language/locale tag; default is not inferred from field names |

`text` is kept verbatim for evidence and audit. Normalized retrieval text is a separate deterministic output.

### `EstateSnapshot`

| Field | Meaning |
|---|---|
| `snapshot_id` | Immutable Bindofell ID for a loaded estate snapshot |
| `dataset_id` | Namespaced identity for the dataset/metadata source |
| `source_name`, `source_version`, `source_revision` | Human-readable source and upstream version/commit |
| `source_uri` | Canonical location used to acquire the source |
| `source_digests` | Sorted list of source path and SHA-256 pairs |
| `schema_version` | Bindofell serialization version |
| `tables`, `fields`, `relationships` | The complete validated metadata universe for this snapshot |

An estate snapshot is immutable after loading. A source update creates a new snapshot ID and never silently mutates an existing benchmark run.

### `Dataset` and `Table`

`Dataset` describes the namespace, name, version, source, retrieval date and applicable terms for a metadata source. `Table` carries a stable `TableId`, the qualified physical table address, the source-provided name, description/guidance fields, and metadata attributes. Table-level context is not copied into fields as if it were field metadata.

### `PhysicalField`

`PhysicalField` has a `FieldId`, parent `TableId`, source-provided column name, qualified physical address, data type, nullability/requiredness when supplied, primary-key membership, and source metadata attributes. Optional metadata includes description, user guidance, ETL conventions and a raw source attribute map. Missing optional metadata remains missing; the adapter does not invent descriptions.

### Relationship metadata

`Relationship` has a namespaced ID, source and target field ID lists, relationship type (for example foreign key), optional cardinality, and evidence pointing to the source constraint. Lists support composite keys. A relationship cannot refer to an unknown field in the same snapshot.

### `Evidence`

Evidence is a typed, attributable record. It contains an evidence ID, evidence kind, source asset, source locator (file plus row/column or JSON pointer), source digest, metadata attribute name, and the relevant source value or a bounded excerpt. For deterministic computation, store the named computation and version, input IDs, and parameters. For a model result, store model identifier/revision, inference configuration, and the output reference. Evidence must let a reviewer trace a candidate claim to source metadata or a reproducible computation.

### `SemanticBinding`, `DirectBinding`, and future `DerivedBinding`

`SemanticBinding` has a versioned kind discriminator. The required v0.1 kind is `DirectBinding`, mapping a requirement to one physical field ID. Reserve `DerivedBinding` for a named output, input field IDs, an opaque expression/formula reference, grain and evidence. An optional serialization-only envelope may preserve that metadata; it neither parses nor executes expressions. No expression engine, formula generation, correctness evaluation or lineage engine belongs in B01–B04. Unsupported binding kinds fail explicitly at the v0.1 retrieval/evaluation boundary.

“Needs clarification” and “no match” are outcome-classification labels, not binding kinds. They cannot be encoded as empty or fabricated `SemanticBinding` objects, and a ranked list alone does not establish either label. An optional outcome decision records its separate rule ID/version, inputs, configuration and rationale; without such a rule, classification is marked not evaluated.

### `BindingCandidate`

`BindingCandidate` contains the requirement ID, snapshot ID, candidate binding/field ID, rank, raw score, method ID/configuration, and evidence list. Raw scores are kept as raw method outputs. They are not exposed as confidence or calibrated correctness probabilities.

### `EvaluationCase` and `GroundTruthMapping`

`EvaluationCase` contains case ID, snapshot ID, business requirement, task label (`direct`, `no_match`, `needs_clarification`), split-group ID, protocol version, annotation grade (`provisional_curator` or `independently_validated`) and review state. `GroundTruthMapping` contains the task-specific accepted alternative field IDs or no-match/clarification annotation, source evidence, rationale, rejected plausible candidates with reasons, and curator/independent-review provenance. Both contracts belong only to `benchmark/models.py` in B02; B01 does not implement them. A case that requires multiple fields simultaneously is outside the v0.1 direct-field metric and must be represented as a future composite/derived track.

Task labels are mutually exclusive. A no-match case has no valid target in the snapshot. A clarification case has at least two plausible targets and must identify the missing business dimension needed to select one. Neither is encoded as an empty gold list without a task label and reason.

## Retrieval text is not source metadata

The adapter stores source attributes in their original typed form. A `SearchDocument` is a derived, deterministic representation containing a field ID and named text channels such as `field_name`, `field_description`, `table_name`, and `table_description`. It records a serializer ID/version and field-level provenance. Ablation profiles select channels without mutating source metadata:

1. `names`: table and field names only;
2. `field_descriptions`: names plus the field description/guidance present in source metadata;
3. `table_context`: the preceding channels plus table description/guidance.

Empty channels are omitted with the omission recorded; no fake placeholder text is introduced. Relationships are represented as structured metadata and are not silently appended to every lexical or embedding document.

## Validation invariants

- Snapshot IDs and field IDs are unique; every field points to one known table.
- Each field ID derives from a complete qualified address, not its display name alone.
- Relationship endpoints exist and are within the snapshot.
- Source values and retrieval text remain separate.
- Every scored candidate refers to the same snapshot used by its evaluation case.
- Ranks are positive integers, raw scores are finite numbers, and method/configuration IDs are recorded.
- Direct-binding gold IDs and Task C plausible IDs exist in the case snapshot and eligible candidate universe. Out-of-universe references fail pre-scoring validation or cause an explicitly reported, method-independent case exclusion; they are not retrieval misses. Task B and C cannot contain a direct gold mapping.
- An independently validated release requires two independent annotations and adjudicator sign-off; resolved provisional curator cases can support separately labeled engineering experiments.
- Optional/missing metadata remains explicit and cannot cause a loader to silently substitute naming conventions.

## Serialization and versioning

B01 should define a versioned JSON estate format with a `schema_version` and round-trip tests. Unknown additive source metadata may be retained in a namespaced extension map; a breaking contract change requires a schema-version increment and a documented migration. Do not add database-specific objects or a graph database abstraction.
