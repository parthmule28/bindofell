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
- Task B (no match) and Task C (needs clarification) have distinct labels and support counts; each class's precision/recall/F1 counts predictions across the full evaluation set.
- Independently validated gold requires two independent annotations and adjudicator sign-off. Engineering milestones may use synthetic fixtures or explicitly provisional curator-grade cases; SQL references and retriever output are not gold by themselves.
- Do not commit source data while its redistribution rights are unresolved; fetch locally and record source/revision/checksum.
- Do not add LangGraph, autonomous agents, graph databases, LLM SQL generation, custom model training, production API server or web UI.
- Do not set performance targets or claim improvement before measurements exist.
- Keep B01–B04 sequential; each work package has its own review and verification gate.

## Review focus

- Duplicate qualified field addresses or a missing catalog/schema segment must be rejected before an ambiguous ID enters an estate.
- Missing descriptions and optional constraints must remain missing rather than be filled with guessed text or naming conventions.
- Foreign-key metadata with a missing endpoint must fail snapshot validation.
- Gold/plausible IDs outside a snapshot or eligible universe, unresolved annotations, and a case split across leakage groups must not be scored. Fail validation or record an explicit method-independent case exclusion; ineligible gold is not a retrieval miss.
- Ranking/serialization reproducibility and variable latency/timestamps have separate comparison rules. Empty rankings and score ties must have deterministic rank handling; optional classification metrics must count false positives against either other class.

## Research corpus provenance and versioning

The 50-paper canonical ledger and 23 benchmark records are reported by the planning handoff, not verified counts in this checkout. Neither the PR branch nor the attached workspace contains the research ledger files named in the B00 request (`papers.csv`, `methods_matrix.csv`, `benchmarks.csv`, research README and supporting notes). Do not reconstruct them from memory or create substitute entries.

When the existing research workspace is supplied, reference it through a version-controlled `research/ledger.lock.json` (a planned file, not present in B00). Record the corpus ID/version, canonical repository URL plus full immutable commit and file paths, or an exact exported archive URL/path plus SHA-256; record per-file SHA-256, freeze/retrieval dates, access/redistribution terms and reported versus verified record counts. Include only files actually received and inspected. Retain an external immutable reference if copying the corpus is not authorized.

Repository citations and experiment manifests must identify that corpus version/reference and lock digest. Change the corpus version and lock in a reviewed commit when the evidence freeze changes; dataset snapshots and software versions remain independent. The unresolved handoff is the actual ledger location/export and its immutable revision. Until supplied, mark research provenance unavailable and avoid claims of verified coverage of those 50 papers. After B00 approval, engineering milestones may still proceed with synthetic/provisional inputs without inventing research artifacts.

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
- `src/bindofell/domain/models.py` — sole owner of `BusinessRequirement`, `EstateSnapshot`, `Dataset`, `Table`, `PhysicalField`, `Relationship`, `Evidence`, `SemanticBinding`, `DirectBinding` and `BindingCandidate`. A future `DerivedBinding` envelope may preserve an opaque expression reference and input IDs only; no expression parser/execution engine. `EvaluationCase` and `GroundTruthMapping` are owned by B02's `benchmark/models.py` and are not implemented here.
- `src/bindofell/metadata/loader.py` — versioned JSON read/write and validation for a generic local estate snapshot.
- `src/bindofell/metadata/adapters/omop.py` — parse the pinned `OMOP_CDMv5.5_Field_Level.csv` and `OMOP_CDMv5.5_Table_Level.csv`; map keys, types, descriptions and relationship metadata without renaming source labels.
- `src/bindofell/retrieval/documents.py` — deterministic `SearchDocument` plus named metadata channels and versioned serializer profiles.
- `scripts/fetch_omop_metadata.py` — fetch the exact release inputs locally, verify the tag against reviewed commit `ba3dc1b651cc243279052bca3d051485c3ec1136` and source paths, and write a SHA-256 source manifest. Record the package's Apache 2.0 declaration; complete component/notice checks before bundling upstream files. Do not check in CSVs by default.
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

**Rollback/review:** if selected component terms remain unresolved, keep adapter and synthetic fixtures and exclude that component from redistribution; keep reconstruction scripts and local acquisition subject to applicable terms. Review parsed counts and IDs against source CSV rows before accepting the adapter. The package's Apache 2.0 declaration is established evidence, not an unresolved missing license.

## B02 — Benchmark and evaluation

**Outcome:** versioned case/gold contracts, leakage-safe split validation, metric calculations and canonical per-case records. Synthetic fixtures and a resolved, explicitly provisional curator-grade pilot can support engineering acceptance; independently validated gold is a separate release gate.

**Files to create:**

- `src/bindofell/benchmark/models.py` — sole owner of `EvaluationCase`, `GroundTruthMapping`, case labels, annotation grade/review state and split-group identity; import B01 domain contracts rather than redefining them.
- `src/bindofell/benchmark/io.py` — versioned JSONL import/export and validation.
- `src/bindofell/benchmark/splits.py` — grouped deterministic train/validation/test split validation and manifest serialization.
- `src/bindofell/evaluation/contracts.py` — sole owner of per-case ranking results, optional outcome decisions and aggregate metric records. B03's `experiments/manifest.py` owns the run manifest.
- `src/bindofell/evaluation/metrics.py` — Top-1, case Recall@5, MRR, candidate-universe coverage audit, and optional no-match/clarification metrics across the full evaluation set, following the benchmark's TP/FP/FN and null-denominator definitions.
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
7. `test_gold_outside_eligible_universe_fails_or_records_explicit_case_exclusion`, including a partially eligible alternative set; never score it as a miss.
8. `test_outcome_metrics_count_both_other_classes_as_false_positives`, covering the full A/B/C confusion matrix and false negatives to either other class.
9. `test_metric_zero_denominators_emit_null_with_counts`, including empty A, no predictions of a class and no true members of a class.
10. `test_annotation_grade_prevents_mixing_provisional_and_validated_results` and validated-gold release without two independent annotations/adjudicator sign-off.
11. `test_runner_preserves_case_candidates_evidence_and_raw_scores`.

**Expected behavior and edge cases:**

- Duplicate case IDs, invalid task labels and duplicate candidate ranks are rejected. Out-of-snapshot/universe references and unresolved cases fail pre-scoring validation or are explicitly excluded before any compared method runs; exclusions retain IDs and reasons.
- A grouped split never separates related paraphrases/template families. If grouping prevents the requested percentages, save actual partition counts and explain rather than leak.
- Empty rankings score zero only on eligible answerable cases. A correct item below rank five affects MRR but not Recall@5. Any accepted alternative is a direct hit; universe coverage is a separate eligibility audit.
- Each optional classification rule must predict every evaluated A/B/C case. Report B and C separately using all three true classes for false positives; no rule means classification not evaluated. A generic abstention cannot replace their metrics.

**Dependencies:** B01 domain/snapshot contracts; no additional runtime dependency expected. Add no sample OMOP labels to tests.

**Verification commands:** `uv run pytest tests/unit/benchmark tests/unit/evaluation -q`; `uv run ruff check`; `uv run pyright`.

**Acceptance criteria:** synthetic/provisional fixtures exercise all metric formulas, class confusions and zero denominators; split validator catches group leakage; ineligible gold fails or is explicitly excluded; valid but unretrieved gold and alternative targets score as specified; outputs retain provenance and grade. Independent review is required to release independently validated gold, not to finish the B02 evaluator.

**Documentation:** publish the annotation protocol, gold schema, split manifest format and exact metric formulas. For real annotations, record actual annotator roles/qualifications and unresolved disagreements.

**Scope exclusions:** source SQL auto-labeling, generated “independent” gold, model training, threshold selection on test, statistical performance targets.

**Rollback/review:** benchmark schema changes require a version bump and migration note. Provisional cases may appear only in separately labeled provisional experiments/releases; promotion to independently validated gold requires the full independent annotation and adjudicator gate. Unresolved cases remain unscored at either grade.

## B03 — Lexical baseline and CLI

**Outcome:** end-to-end BM25 retrieval baseline with `bindofell search` and `bindofell evaluate`, deterministic ranked candidates, Task A metrics, manifests and per-case output. B/C outcome classification is a separate optional experiment and is not a required BM25 capability.

**Files to create:**

- `src/bindofell/retrieval/lexical.py` — BM25 index/build/query, deterministic normalization/tokenization and method configuration.
- `src/bindofell/experiments/manifest.py` — sole owner of run manifests: source, benchmark/annotation grade, research corpus reference/digest (or unavailable status), dependency, method, environment and timestamp metadata. Identify static comparison fields separately from runtime observations.
- `src/bindofell/cli.py` — `argparse` commands for loading a local estate/case file and writing result artifacts.
- `src/bindofell/__main__.py` — `python -m bindofell` entry point.
- `src/bindofell/experiments/run.py` — connect B01 adapter/documents, B02 evaluator, BM25 and output writers. Any optional explicit outcome rule is applied separately from `retrieval/lexical.py` and reported as experimental classification.
- `tests/unit/retrieval/test_lexical.py`, `tests/unit/experiments/test_manifest.py`, `tests/integration/test_cli_search.py`, `test_cli_evaluate.py`.
- `docs/usage/cli.md` and README quickstart with synthetic inputs only until real benchmark rights/annotations are approved.

**Commands and output contract:**

- `bindofell search --estate PATH --requirement TEXT --profile names|field_descriptions|table_context --top-k N --output PATH` writes ordered field IDs, names, raw BM25 scores, evidence references and run config.
- `bindofell evaluate --estate PATH --cases PATH --split train|validation|test --profile PROFILE --output-dir PATH` writes `metrics.json`, `cases.jsonl`, and `run.json` with Task A rank metrics/denominators, method config, source hashes, annotation grade, dependency lock and environment data. Default outcome classification is not evaluated.
- Scores are not “confidence” or “probability”. Optional no-match/clarification heuristics require explicit rule/version, inputs, label mapping, parameters and conflict handling; tune only on train/validation and freeze before test. Emit a separate experimental classification report across the full A/B/C set. No heuristic or reliable detection claim is required for B03 acceptance.

**Tests to write first:**

1. `test_bm25_ranks_relevant_field_deterministically`.
2. `test_equal_scores_break_ties_by_canonical_field_id`.
3. `test_profile_changes_text_but_not_candidate_universe`.
4. `test_empty_query_and_empty_estate_return_valid_explicit_results`.
5. `test_cli_search_emits_ranked_physical_ids_and_evidence`.
6. `test_cli_evaluate_writes_metrics_manifest_and_per_case_rows`.
7. `test_cli_rejects_unknown_snapshot_or_invalid_gold_before_scoring`.
8. `test_without_explicit_decision_rule_classification_is_not_evaluated`, including empty and zero-score rankings.
9. `test_reproducibility_projection_excludes_latency_and_timestamps` while comparing static manifests, documents, candidate order/scores, evidence and non-timing metrics.

**Expected behavior and edge cases:** stable tokenization and ranking under the same locked environment; zero-score ties deterministic; missing text channels omitted; malformed inputs fail before index creation; output records candidate universe and all per-case results. Empty/low-score lists do not prove no-match, and close/tied scores do not prove semantic ambiguity. Timing/timestamp fields remain variable and are excluded from deterministic equality projections.

**Dependencies:** B01 and B02; add a locked BM25 implementation such as `bm25s` after compatibility review. Keep the CLI on `argparse` unless an existing convention is discovered in a populated repository before implementation.

**Verification commands:** `uv run pytest tests/unit/retrieval tests/unit/experiments tests/integration/test_cli_search.py tests/integration/test_cli_evaluate.py -q`; `uv run ruff check`; `uv run pyright`; `uv run bindofell --help`.

**Acceptance criteria:** both commands run from a clean locked environment using synthetic/resolved provisional fixtures; rankings return namespace-aware table-column IDs, evidence and raw scores; test and validation use identical candidate universe rules; Task A metrics and all per-case rankings are written; static reproducibility projections match. Optional classification is explicitly experimental and evaluated separately; B/C accuracy is not a milestone requirement. Independently validated benchmark claims retain the release gate.

**Documentation:** CLI arguments, output formats, retrieval/classification separation and optional heuristic policy, source fetch instructions, reproducible synthetic example, annotation grade and manifest comparison fields.

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

**Expected behavior and edge cases:** missing local model files produce an actionable error; compare dense scores with a declared numerical tolerance/runtime policy and still check candidate order, reporting rank changes. BM25/RRF ordering and canonical serialization are deterministic under the same supported environment; latency and timestamps are observations. Non-finite vectors fail; cache keys cannot reuse vectors across changed weights or metadata profiles; all methods use the same split, annotation grade and candidate universe. Record device, precision and batch size; uncalibrated scores do not establish B/C labels.

**Dependencies:** B03; one approved local embedding runtime/model package and immutable model files. Lock exact package/model revisions and hashes only after review. Unit tests use fake vectors and do not download a model.

**Verification commands:** `uv run pytest tests/unit/retrieval tests/unit/experiments -q`; `uv run pytest tests/integration/test_dense_local_model.py -q` with approved local weights; `uv run ruff check`; `uv run pyright`; run the identical saved split through BM25, dense and RRF and inspect per-case JSONL and all three metadata profiles.

**Acceptance criteria:** dense/RRF result schemas match the lexical interface; every method uses identical eligible IDs, split and case set; model, weight and tokenizer digests appear in the run manifest; no runtime network dependency; ablations isolate names, field descriptions and table context; no numerical improvement target is imposed.

**Documentation:** exact model license/access and offline cache setup, RRF parameters, vector/cache reproducibility, device settings, metadata ablation definitions and test command.

**Scope exclusions:** model fine-tuning, LLM-generated explanations, SQL generation, agent orchestration, changing the public gold set based on model outputs.

**Rollback/review:** dense and hybrid modules remain optional imports so BM25 CLI works without model dependencies. If model license, reproducibility or local execution fails review, keep B04 gated and retain B03 as the valid baseline.

## Final review gate

After B00 review, execute B01, B02, B03 and B04 sequentially. Each work package must meet its acceptance criteria and pass its listed verification before the next begins. B01 must not start from this document alone; the user must first review/approve the B00 source assessment, domain contracts and benchmark protocol. Engineering gates can use synthetic/provisional fixtures; releasing independently validated gold/results requires the separate independent review gate. The embedding model decision is a separate B04 gate. Preserve exact source files, code revisions, case/gold grade and version, research provenance status and per-case outputs for every reported result; compare deterministic projections rather than variable runtime observations.
