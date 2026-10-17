# Bindofell B01–B04 Implementation Plan

> **For agentic workers:** Use the repository's approved execution workflow after the B00 documents are reviewed. Steps use checkbox syntax for tracking. B01 is explicitly gated on B00 review; this plan is not permission to start implementation.

**Goal:** Build Bindofell v0.1 as a reproducible table-column retrieval and evaluation system over a frozen metadata estate.

**Architecture:** Use one small Python package under `src/bindofell` with domain, metadata, benchmark, retrieval, evaluation and CLI modules. Keep source metadata separate from deterministic search documents, keep benchmark annotations independent from retrieval, and write per-case experiment outputs with source and runtime provenance.

**Tech Stack:** Python, `uv`, `pyproject.toml`, Pydantic at data boundaries, `pytest`, Ruff, Pyright, BM25 (`bm25s` or a compatible locked implementation), a pinned local embedding model in B04, and a standard-library `argparse` CLI. The selected embedding model and inference library are B04 review-gated decisions.

**Specs:** [Core Domain Contracts](../design/0001-bindofell-core.md), [Benchmark Specification](../design/0002-benchmark-v0.1.md), [Public Dataset Source Assessment](../datasets/source-assessment.md).

## Global constraints

- B00 review must complete before B01 starts.
- v0.1 is reproducible table-column retrieval and evaluation, not a production semantic layer.
- Candidate IDs include a namespace and qualified table/column address; a column name alone is never identity.
- Source metadata is separate from lexical/embedding serialization.
- Task B (no match) and Task C (needs clarification) have distinct labels, predictions and denominators.
- Gold is independently curated and adjudicated; SQL references and retriever output are not gold by themselves.
- Do not commit source data while its redistribution rights are unresolved; fetch locally and record source/revision/checksum.
- Do not add LangGraph, autonomous agents, graph databases, LLM SQL generation, custom model training, production API server or web UI.
- Do not set performance targets or claim improvement before measurements exist.
- Keep B01–B04 sequential; each work package has its own review and verification gate.

## Review focus

- Duplicate qualified field addresses or a missing catalog/schema segment must be rejected before an ambiguous ID enters an estate.
- Missing descriptions and optional constraints must remain missing rather than be filled with guessed text or naming conventions.
- Foreign-key metadata with a missing endpoint must fail snapshot validation.
- Gold IDs outside a snapshot, unresolved annotations, and a case split across leakage groups must not be scored.
- An empty ranked list, score ties, absent candidates, no-match decisions and clarification decisions must produce deterministic outputs and correct denominators.

---

## Proposed package layout

Create these boundaries only as each work package needs them:

```text
pyproject.toml
uv.lock
src/bindofell/
  __init__.py
  domain/models.py
  metadata/loader.py
  metadata/adapters/omop.py
  retrieval/documents.py
  retrieval/lexical.py
  retrieval/dense.py
  retrieval/hybrid.py
  benchmark/models.py
  benchmark/io.py
  benchmark/splits.py
  evaluation/contracts.py
  evaluation/metrics.py
  evaluation/runner.py
  experiments/manifest.py
  cli.py
tests/
  unit/...
  fixtures/...
docs/...
scripts/fetch_omop_metadata.py
```

Do not create a module early unless its owning work package needs it. The `data/` directory should contain only explicitly approved fixtures/annotations; fetched upstream files remain local and ignored until rights are settled.

## B01 — Domain and metadata

**Outcome:** versioned domain contracts, a generic local metadata snapshot loader, one OMOP v5.5.0 metadata adapter and deterministic field-document serialization. No retriever or real gold annotations.

**Files to create:**

- `pyproject.toml`, `uv.lock`, `src/bindofell/__init__.py` — package metadata, locked environment and entry-point namespace; keep CLI entry point declaration ready but add the command implementation in B03.
- `src/bindofell/domain/models.py` — Pydantic boundary/domain models: `BusinessRequirement`, `EstateSnapshot`, `Dataset`, `Table`, `PhysicalField`, `Relationship`, `Evidence`, `SemanticBinding`, `DirectBinding`, future `DerivedBinding`, `BindingCandidate`, `EvaluationCase`, and `GroundTruthMapping`.
- `src/bindofell/metadata/loader.py` — versioned JSON read/write and validation for a generic local estate snapshot.
- `src/bindofell/metadata/adapters/omop.py` — parse the pinned `OMOP_CDMv5.5_Field_Level.csv` and `OMOP_CDMv5.5_Table_Level.csv`; map keys, types, descriptions and relationship metadata without renaming source labels.
- `src/bindofell/retrieval/documents.py` — deterministic `SearchDocument` plus named metadata channels and versioned serializer profiles.
- `scripts/fetch_omop_metadata.py` — fetch exact release inputs only after license review; resolve the tag to a full commit, verify source paths, write local files and a source manifest with SHA-256 hashes. Do not check in upstream CSVs by default.
- `tests/unit/domain/test_models.py`, `tests/unit/metadata/test_loader.py`, `tests/unit/metadata/test_omop_adapter.py`, `tests/unit/retrieval/test_documents.py` — invalid-input, missing-metadata, identity and deterministic serialization tests.
- `tests/fixtures/omop/` — tiny synthetic CSV/JSON fixtures with deliberately incomplete optional metadata; do not label them as upstream OMOP rows.
- Update `docs/design/0001-bindofell-core.md` and `docs/datasets/source-assessment.md` only if implementation discovery reveals a verified contract/source correction; record the importer's actual table/field counts and source hashes in local generated manifests, not invented prose.

**Tests to write first:**

1. `test_field_id_requires_namespace_and_qualified_address`: reject missing namespace/table/column and reject duplicate IDs.
2. `test_snapshot_rejects_unknown_relationship_endpoint`: invalid FK target fails with a locator-rich error.
3. `test_loader_rejects_unsupported_schema_version_and_malformed_json`: malformed or future-incompatible input is explicit failure.
4. `test_optional_metadata_stays_absent`: blank description/guidance is `None`, not guessed from column name.
5. `test_omop_adapter_maps_required_datatype_keys_and_guidance`: tiny fixture preserves source values and links the expected FK fields.
6. `test_omop_adapter_reports_counts_and_source_provenance`: parsed counts and input SHA-256 are included in snapshot metadata.
7. `test_search_documents_are_stable_and_separate_from_source`: repeat serialization is byte-stable; names/field-description/table-context profiles select only their documented channels.

**Expected behavior and edge cases:**

- CSV required headers are checked before row parsing. Unknown additive source columns are preserved in an extension map or explicitly reported; required identity/type columns cannot be silently dropped.
- Empty required table/column names, duplicate qualified addresses, invalid encodings, bad CSV quoting and unresolved FK targets fail with file and row context.
- Missing description, guidance, key flags or optional datatypes stay absent; no class-word/naming convention is assumed.
- Release fetch must fail if the requested ref no longer resolves to the reviewed commit or a required file differs from a saved digest.

**Dependencies:** `uv`; Pydantic; Python standard-library CSV/JSON/hash tools. Add `pytest`, Ruff and Pyright as locked development dependencies. No network fetch in unit tests.

**Verification commands:** `uv sync --all-groups`; `uv run pytest tests/unit/domain tests/unit/metadata tests/unit/retrieval -q`; `uv run ruff check`; `uv run pyright`.

**Acceptance criteria:** round-trip snapshot serialization; namespace-aware stable IDs; valid FK graph; robust invalid-input errors; OMOP adapter parses the approved v5.5.0 files and records provenance/counts; deterministic serializer profiles; source metadata remains unchanged by serialization; no production retrieval code.

**Documentation:** document snapshot JSON schema, local fetch procedure, source rights gate, metadata channel definitions, and how to regenerate file hashes/count manifests.

**Scope exclusions:** search ranking, actual business gold, external benchmark archives, embeddings, formula execution and API/UI.

**Rollback/review:** if rights remain unresolved, keep adapter and synthetic fixtures but disable public fetch/release workflow and commit no CSV files. Review parsed counts and IDs against source CSV rows before accepting the adapter.

## B02 — Benchmark and evaluation

**Outcome:** versioned case/gold contracts, leakage-safe split validation, metric calculations and deterministic per-case evaluation records. Real gold annotations are added only after independent human review.

**Files to create:**

- `src/bindofell/benchmark/models.py` — case labels, accepted alternatives, evidence, review state and split-group IDs.
- `src/bindofell/benchmark/io.py` — versioned JSONL import/export and validation.
- `src/bindofell/benchmark/splits.py` — grouped deterministic train/validation/test split validation and manifest serialization.
- `src/bindofell/evaluation/contracts.py` — per-case result, run manifest and aggregate metric models.
- `src/bindofell/evaluation/metrics.py` — Top-1, case Recall@5, MRR, candidate coverage/ceiling, no-match metrics and clarification metrics.
- `src/bindofell/evaluation/runner.py` — evaluate method outputs against a frozen case set and candidate universe.
- `tests/unit/benchmark/test_models.py`, `test_io.py`, `test_splits.py`, `tests/unit/evaluation/test_metrics.py`, `test_runner.py`.
- `tests/fixtures/benchmark/toy_estate.json`, `toy_cases.jsonl`, `toy_rankings.jsonl` — fully synthetic fixtures labeled as such.
- `docs/benchmark/annotation-protocol.md` — pilot workflow, annotator fields, adjudication and release version process; update `docs/design/0002-benchmark-v0.1.md` if implementation requires an approved clarification.

**Tests to write first:**

1. `test_case_requires_task_specific_gold_shape`: Task A needs at least one accepted snapshot field; Task B has no target; Task C names at least two plausible candidates and a missing dimension.
2. `test_gold_rejects_field_absent_from_snapshot`.
3. `test_split_rejects_paraphrase_or_template_group_crossing_partitions`.
4. `test_split_is_deterministic_for_recorded_seed_and_manifest`.
5. `test_metrics_handle_correct_incorrect_and_empty_rankings`.
6. `test_metrics_accept_any_of_multiple_gold_alternatives`.
7. `test_candidate_coverage_counts_absent_gold_separately`.
8. `test_no_match_and_clarification_metrics_keep_distinct_denominators`.
9. `test_runner_preserves_case_candidates_evidence_and_raw_scores`.

**Expected behavior and edge cases:**

- Duplicate case IDs, invalid task labels, references outside the snapshot, unresolved annotations and duplicate candidate ranks are rejected.
- A grouped split never separates related paraphrases/template families. If grouping prevents the requested percentages, save actual partition counts and explain rather than leak.
- Empty rankings score zero on answerable cases. A correct item below rank five affects MRR but not Recall@5. Any accepted alternative is a direct hit.
- Task B and Task C are reported separately; reporting a generic abstention cannot replace their metrics.

**Dependencies:** B01 domain/snapshot contracts; no additional runtime dependency expected. Add no sample OMOP labels to tests.

**Verification commands:** `uv run pytest tests/unit/benchmark tests/unit/evaluation -q`; `uv run ruff check`; `uv run pyright`.

**Acceptance criteria:** all requested metrics have explicit formulas and denominators; split validator catches group leakage; absent and multiply acceptable targets behave as specified; outputs preserve case-level predictions and provenance; fixtures are clearly synthetic; no claim of independent annotation is made until humans complete and adjudicate the protocol.

**Documentation:** publish the annotation protocol, gold schema, split manifest format and exact metric formulas. For real annotations, record actual annotator roles/qualifications and unresolved disagreements.

**Scope exclusions:** source SQL auto-labeling, generated “independent” gold, model training, threshold selection on test, statistical performance targets.

**Rollback/review:** benchmark schema changes require a version bump and migration note. Keep provisional human cases out of scored releases until adjudication is complete.

## B03 — Lexical baseline and CLI

**Outcome:** end-to-end BM25 baseline with `bindofell search` and `bindofell evaluate`, deterministic ranking, separate no-match/clarification decisions, metrics, manifests and per-case output.

**Files to create:**

- `src/bindofell/retrieval/lexical.py` — BM25 index/build/query, deterministic normalization/tokenization and method configuration.
- `src/bindofell/experiments/manifest.py` — source, benchmark, dependency, method, environment and timestamp metadata.
- `src/bindofell/cli.py` — `argparse` commands for loading a local estate/case file and writing result artifacts.
- `src/bindofell/__main__.py` — `python -m bindofell` entry point.
- `src/bindofell/experiments/run.py` — connect B01 adapter/documents, B02 evaluator, BM25 and output writers.
- `tests/unit/retrieval/test_lexical.py`, `tests/unit/experiments/test_manifest.py`, `tests/integration/test_cli_search.py`, `test_cli_evaluate.py`.
- `docs/usage/cli.md` and README quickstart with synthetic inputs only until real benchmark rights/annotations are approved.

**Commands and output contract:**

- `bindofell search --estate PATH --requirement TEXT --profile names|field_descriptions|table_context --top-k N --output PATH` writes ordered field IDs, names, raw BM25 scores, evidence references and run config.
- `bindofell evaluate --estate PATH --cases PATH --split train|validation|test --profile PROFILE --output-dir PATH` writes `metrics.json`, `cases.jsonl`, and `run.json` with denominators, threshold/config, source hashes, dependency lock and environment data.
- Default output does not call scores “confidence” or “probability”. No-match and clarification decision rules/thresholds are method-specific, selected on validation and frozen before test.

**Tests to write first:**

1. `test_bm25_ranks_relevant_field_deterministically`.
2. `test_equal_scores_break_ties_by_canonical_field_id`.
3. `test_profile_changes_text_but_not_candidate_universe`.
4. `test_empty_query_and_empty_estate_return_valid_explicit_results`.
5. `test_cli_search_emits_ranked_physical_ids_and_evidence`.
6. `test_cli_evaluate_writes_metrics_manifest_and_per_case_rows`.
7. `test_cli_rejects_unknown_snapshot_or_invalid_gold_before_scoring`.

**Expected behavior and edge cases:** stable tokenization and ranking under the same locked environment; zero-score ties deterministic; missing text channels omitted; malformed inputs fail before index creation; output records candidate universe and all per-case results. A threshold can abstain but raw scores remain uncalibrated ranking values.

**Dependencies:** B01 and B02; add a locked BM25 implementation such as `bm25s` after compatibility review. Keep the CLI on `argparse` unless an existing convention is discovered in a populated repository before implementation.

**Verification commands:** `uv run pytest tests/unit/retrieval tests/unit/experiments tests/integration/test_cli_search.py tests/integration/test_cli_evaluate.py -q`; `uv run ruff check`; `uv run pyright`; `uv run bindofell --help`.

**Acceptance criteria:** both commands run from a clean locked environment; rankings return namespace-aware table-column IDs, evidence and raw scores; test and validation use identical candidate universe rules; metrics and all per-case predictions are written; no performance claims or hidden data copies.

**Documentation:** CLI arguments, output formats, threshold policy, source fetch instructions, reproducible synthetic example and experiment manifest fields.

**Scope exclusions:** dense retrieval, embedding downloads, API server, web UI, SQL generation and online services.

**Rollback/review:** BM25 is isolated behind a retrieval interface. If the selected package breaks the locked environment, swap only the lexical implementation while preserving the method/output contract and rerun identical fixtures.

## B04 — Dense, hybrid and metadata ablations

**Outcome:** locally reproducible dense retrieval, Reciprocal Rank Fusion and controlled metadata-field ablations over the same snapshots/cases/candidate universe as B03.

**Review gate before implementation:** choose and approve one pretrained embedding model, immutable model revision/weight digest, tokenizer, inference library and supported local runtime. This choice is not made in B00. The model must be downloadable before a run and executable without a runtime API call. No model is selected by test-set performance.

**Files to create:**

- `src/bindofell/retrieval/dense.py` — local model loading, batch encoding, deterministic vector normalization and dense ranking.
- `src/bindofell/retrieval/hybrid.py` — rank-based RRF over BM25 and dense rankings; expose `k` and source weights in configuration; no score calibration.
- `src/bindofell/retrieval/embeddings.py` — local cache, model digest validation and cache keying by model/tokenizer revision, document serializer and field ID.
- `configs/embedding-model.json` — approved model ID/revision, hashes, tokenizer, dimensions, normalization, runtime and license reference.
- `tests/unit/retrieval/test_dense.py`, `test_hybrid.py`, `tests/integration/test_dense_local_model.py` (opt-in, requiring pre-cached weights), and `test_ablation_universe.py`.
- `docs/experiments/dense-and-hybrid.md` — model acquisition, offline execution, hardware/dependency recording, ablation table and comparison protocol.

**Tests to write first:**

1. `test_dense_uses_local_revision_without_network_access` using a deterministic fake encoder.
2. `test_embedding_cache_invalidates_on_model_or_serializer_digest_change`.
3. `test_dense_ties_and_non_finite_vectors_fail_deterministically`.
4. `test_rrf_uses_ranks_and_configured_constant_not_raw_score_mixing`.
5. `test_rrf_is_deterministic_when_one_method_omits_a_result`.
6. `test_all_ablation_profiles_use_same_field_id_universe`.
7. `test_names_description_and_table_context_are_separate_profiles`.
8. `test_run_manifest_records_model_revision_weight_hash_and_device`.

**Expected behavior and edge cases:** missing local model files produce an actionable error; dense and RRF ranks are reproducible under fixed model/config; non-finite vectors fail; cache keys cannot reuse vectors across changed weights or metadata profiles; all methods run on the same split and candidate universe. Record device, precision and batch size.

**Dependencies:** B03; one approved local embedding runtime/model package and immutable model files. Lock exact package/model revisions and hashes only after review. Unit tests use fake vectors and do not download a model.

**Verification commands:** `uv run pytest tests/unit/retrieval tests/unit/experiments -q`; `uv run pytest tests/integration/test_dense_local_model.py -q` with approved local weights; `uv run ruff check`; `uv run pyright`; run the identical saved split through BM25, dense and RRF and inspect per-case JSONL and all three metadata profiles.

**Acceptance criteria:** dense/RRF result schemas match the lexical interface; every method uses identical eligible IDs, split and case set; model, weight and tokenizer digests appear in the run manifest; no runtime network dependency; ablations isolate names, field descriptions and table context; no numerical improvement target is imposed.

**Documentation:** exact model license/access and offline cache setup, RRF parameters, vector/cache reproducibility, device settings, metadata ablation definitions and test command.

**Scope exclusions:** model fine-tuning, LLM-generated explanations, SQL generation, agent orchestration, changing the public gold set based on model outputs.

**Rollback/review:** dense and hybrid modules remain optional imports so BM25 CLI works without model dependencies. If model license, reproducibility or local execution fails review, keep B04 gated and retain B03 as the valid baseline.

## Final review gate

After B00 review, execute B01, B02, B03 and B04 sequentially. Each work package must meet its acceptance criteria and pass its listed verification before the next begins. B01 must not start from this document alone; the user must first review/approve the B00 source assessment, domain contracts and benchmark protocol. The embedding model decision is a separate B04 gate. Preserve exact source files, code revisions, gold version and per-case experiment outputs for every reported result.
