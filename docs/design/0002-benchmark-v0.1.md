# Bindofell v0.1 Benchmark Specification

**Status:** B00 proposal for review.
**Scope:** reproducible retrieval and evaluation of direct physical table-column candidates. The first recommended metadata estate is the locally acquired, versioned OMOP CDM v5.5.0 dictionary candidate; benchmark annotations remain uncreated until independent annotators review the source and rights gate.

## Task definitions

Every case binds to one frozen `EstateSnapshot` and one candidate universe containing all included physical fields in that snapshot.

### Task A — Direct Binding

A natural-language business requirement has at least one valid direct physical field in the snapshot. `accepted_field_ids` lists one or more acceptable alternative table-column IDs. If several fields are all required simultaneously to define a formula or composite output, this is not a direct-field v0.1 case; reserve it for a future derived/composite track.

### Task B — No Match

No valid physical representation exists in the supplied snapshot. The annotator must state the scope checked and why plausible candidates are invalid or insufficient. This is not “the retriever failed to find the answer”; it is an independently labeled property of the frozen estate.

### Task C — Needs Clarification

At least two candidates are valid for different interpretations, but the requirement lacks a business dimension required to select one. The annotation names the plausible field IDs and the missing dimension (for example, event type, date role, population or grain). A clarification case is not no-match: valid candidates exist, but the requirement does not select one.

### Derived bindings

Derived KPI/formula bindings are a future track. v0.1 may preserve the future `DerivedBinding` contract but does not generate formulas/SQL, prove expression equivalence, or score lineage completeness.

## Candidate universe and case representation

- The candidate universe is the complete set of eligible `PhysicalField` IDs in the named snapshot after one documented, method-independent eligibility rule. Retrieval methods may reorder it, but may not change it.
- Every case records `case_id`, `snapshot_id`, task label, verbatim requirement, `split_group_id`, accepted field IDs (Task A), plausible field IDs and missing dimension (Task C), or no-match rationale (Task B), evidence references, annotation/adjudication state, and provenance.
- All accepted IDs must resolve in the snapshot. Alternative IDs are OR alternatives: any one is a valid direct answer. A case that requires multiple simultaneous fields is excluded from Task A and recorded for future-track review.
- No-match and clarification cases remain distinct labels and distinct metric denominators.

## Feasibility and case plan

Run an initial **15–20 case annotation pilot** against the chosen metadata snapshot. Use it to check whether source descriptions support clear decisions, whether annotators can identify plausible-but-invalid fields, and whether no-match/clarification can be distinguished reliably. Review and revise instructions before expanding. The pilot is not automatically merged into the final gold set; retain cases only after the same independent review and adjudication process.

The provisional **100-case target** is:

| Case family | Target | Feasibility against OMOP metadata |
|---|---:|---|
| Straightforward direct mappings | 30 | Feasible: table/field descriptions and guidance provide source evidence |
| Semantic synonyms/abbreviations | 20 | Feasible with independent human wording and documented rationale |
| Near-duplicate table-column candidates | 20 | Feasible: repeated identifiers, concept IDs, dates and event variants provide plausible distractors |
| No match | 15 | Feasible only with snapshot-bounded scope and exhaustive human review |
| Underspecified / needs clarification | 15 | Feasible where source metadata supports multiple valid roles but the prompt omits the distinguishing dimension |

These counts are planning targets, not a claim that cases already exist or that an expert has verified them. The pilot may change the distribution if a category cannot be annotated consistently. Publish per-category denominators and uncertainty; do not invent a score target.

## Annotation procedure

1. **Freeze the estate.** Record source version/revision, file digests, parser version, candidate-universe manifest and eligibility rules before writing requirements.
2. **Author requirements independently.** Human authors create business-language requirements without querying the evaluated retriever, dense model, benchmark predictions, or their scores. Record author and source basis. SQL from BIRD/Spider may help a curator find fields, but SQL references are never copied into gold without independent semantic review.
3. **Annotate independently.** At least two annotators label every final gold case independently, without seeing each other's decisions or retriever rankings. They inspect the same frozen metadata and candidate IDs. Record their qualifications and domain experience; do not call annotation expert-verified unless that qualification and review actually occurred.
4. **Capture evidence.** For each accepted target, cite source metadata by source file digest, table/field locator and attribute (description, guidance, datatype, relationship, key, or other field). For Task B, cite the scope and examined plausible candidates. For Task C, cite every plausible candidate and the missing dimension.
5. **Record alternatives and rejections.** Accepted alternative field IDs are explicit. Record plausible rejected candidates and one or more reasons: wrong entity, grain, time role, population, semantic domain, identifier-vs-value role, unsupported interpretation, or other stated reason. Do not make the rationale depend on retriever rank.
6. **Adjudicate disagreements.** A third reviewer reviews disagreements against the source evidence, records the decision and rationale, and may leave a case unresolved. Unresolved cases are excluded from scored gold until resolved; preserve annotation history rather than silently overwriting it.
7. **Audit task separation.** Re-check that every Task B case has no valid candidate and every Task C case has multiple plausible valid candidates plus a specific missing dimension. Move cases between labels only with recorded adjudication.
8. **Version the gold.** Save annotation protocol version, case IDs, annotator decisions, adjudication and gold digest. Never revise a published gold set in place; create a new version and document changes.

If independent qualified review is unavailable, report the cases as a provisional curator set, not expert-verified gold. The retriever under evaluation must never generate its own supposedly independent gold labels.

## Split and leakage controls

- Before split assignment, create groups linking paraphrases of the same requirement, the same normalized business concept, near-identical accepted-target families, same authoring template family, and all variants generated from one seed/template. A group cannot cross partitions.
- Keep synonym transformations, templated wording, and derived variants of a prompt in one group. Do not author one paraphrase for train and a near-copy for test.
- Group related near-duplicate target cases together where feasible; all alternatives for a case stay in one group. Candidate metadata may appear in every run because it is the fixed estate; query text or labels from another partition may not.
- Use a recorded deterministic grouped, stratified **60/20/20 train/validation/test** assignment for the 100-case target, with a recorded seed and split manifest. The pilot can be used to refine instructions, but it must not be reused as a hidden test set after retriever-driven iteration.
- If category constraints make the requested proportions impossible without splitting a group, preserve group integrity, record actual counts, and report them. Do not force leakage to hit a target percentage.
- Any model/index fitting, no-match threshold choice, clarification threshold choice, or parameter selection uses train/validation only. Freeze these settings before test evaluation.

## Evaluation protocol and denominators

Let `A` be the set of independently adjudicated Task A cases, `B` Task B cases, and `C` Task C cases. Report each denominator and the case IDs included/excluded. For Task A case `i`, let `G_i` be its accepted alternative field IDs and `R_i` its ranked results, ordered by descending raw score then canonical `FieldId` ascending. This deterministic ID tie-break makes output stable; tied scores are not evidence of equal correctness probability.

| Metric | Definition and denominator |
|---|---|
| Top-1 exact table-column accuracy | `sum(1[R_i[1] in G_i]) / |A|`. Empty rankings count incorrect. “Exact” means the returned field ID exactly matches an accepted ID, including its namespace/table. |
| Recall@5 (case hit rate) | `sum(1[set(R_i[1:5]) intersects G_i]) / |A|`. Alternative accepted IDs are OR alternatives; returning any one in the first five is a hit. |
| MRR | `sum(1 / rank_i) / |A|`, where `rank_i` is the first rank whose field ID is in `G_i`; zero if none is retrieved. |
| Candidate coverage / retrieval ceiling | `sum(1[G_i intersects U_i]) / |A|`, where `U_i` is the complete eligible candidate universe for the case. This is the maximum answerable-case hit rate any ranking method can attain on that universe. Also report absent-gold count and IDs. |
| No-match detection | On `B`, report precision, recall and F1 for the `NO_MATCH` decision, with `|B|` and all predicted no-match cases. Report false no-match rate on `A` separately. |
| Clarification detection | On `C`, report precision, recall and F1 for `NEEDS_CLARIFICATION`, with `|C|`. Report false-clarification rate on `A` separately. |

If the run also reports three-way outcome accuracy, keep it secondary and include the full `DIRECT / NO_MATCH / NEEDS_CLARIFICATION` confusion matrix. Do not combine Task B and C into a generic abstain class for the primary results.

### Thresholds, ties and score interpretation

- Retrieval returns ranked field IDs and raw method scores. No BM25, vector cosine or RRF score is a calibrated probability.
- The baseline may choose a no-match or clarification decision using a documented method-specific rule/threshold. Choose thresholds only on validation, record them, and freeze them before test. Report sensitivity to any threshold sweep separately; never select a threshold from test results.
- Stable serialization sorts exact score ties by canonical field ID ascending. This tie rule is applied before all rank metrics and saved in the experiment manifest.
- Every method and ablation uses the same snapshot, eligibility policy, case IDs, split, and full candidate universe. A method may return fewer top results, but its index cannot drop candidates silently.

## Latency, reproducibility and outputs

Record index-build time separately from query latency. Measure per-case query latency with a monotonic clock; publish median and p95 for the evaluated split, warm/cold state, number of cases, candidate count, device/CPU/GPU, thread count, Python and OS versions. Do not set a pass threshold in B00.

Each run preserves:

- per-case verbatim requirement, task label (evaluation only), gold IDs, prediction/outcome, ranked candidates, raw scores, ranks, evidence, decision rationale and latency;
- aggregate metrics with explicit denominators and excluded-case reasons;
- source snapshot and file digests, dataset and gold versions/digests, split manifest and seed;
- Git revision/dirty state, Python/dependency lock, method and serializer versions, ablation profile, model ID/revision/weight digest when applicable, hardware/runtime settings, and UTC run timestamp.

Store deterministic JSONL per-case results plus a JSON run manifest and metrics summary. Keep identifiers and evidence references in output so a reviewer can reconstruct why a candidate appeared. Do not keep only aggregate scores.

## Planned metadata ablations

Use the same field IDs and candidate universe for:

1. table and field names only;
2. names plus field-level description/guidance;
3. the preceding text plus table description/guidance.

Record missing-channel counts for each profile. Do not compare an ablation that silently changes which candidate fields are indexed. Relationships/keys may be reported as a later ablation after a separate design review.

## Limitations

The target set is small and standard-specific. Scores describe these snapshots, tasks, annotators and splits; they are not universal enterprise binding performance. Report category-level counts and uncertainty, preserve all per-case outputs, and avoid over-interpreting differences when denominators are small.
