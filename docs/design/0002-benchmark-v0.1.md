# Bindofell v0.1 Benchmark Specification

**Status:** B00 proposal for review.
**Scope:** reproducible retrieval and evaluation of direct physical table-column candidates. The first recommended metadata estate is the locally acquired, versioned OMOP CDM v5.5.0 dictionary candidate. Annotations are not yet created; a solo curator may build an explicitly provisional pilot, while an independently validated gold release requires the review gate below. Source rights and redistribution checks apply to either grade.

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
- All accepted and plausible IDs must resolve in both the snapshot and its eligible universe. An out-of-universe reference fails validation, even if another accepted alternative is eligible. An explicit, method-independent exclusion of the entire affected case may be recorded before scoring; never silently drop an alternative, relabel a case as no-match, or count ineligible gold as a retrieval miss. Alternative IDs are OR alternatives: any one is a valid direct answer. A case that requires multiple simultaneous fields is excluded from Task A and recorded for future-track review.
- No-match and clarification remain distinct labels. Each class has its own support count, but classification precision/recall/F1 uses predictions across the full evaluation set, as defined below.

## Feasibility and case plan

Run an initial **15–20 case annotation pilot** against the chosen metadata snapshot. A solo maintainer may author and resolve this as a **provisional curator-grade pilot** (`annotation_grade=provisional_curator`), recording curator identity, protocol, evidence, alternatives, rejection reasons and unresolved cases. It provides no independent or expert verification. Use it to check whether descriptions support decisions and whether no-match/clarification labels are feasible; revise instructions before expanding. Promotion to independently validated gold requires the independent annotation and adjudication process, including for retained pilot cases.

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
2. **Author requirements independently of retrieval.** Human authors create business-language requirements without querying the evaluated retriever, dense model, benchmark predictions, or their scores. Record author and source basis. SQL from BIRD/Spider may help a curator find fields, but needs separate human semantic assessment at the declared annotation grade, including independent review for validated gold.
3. **Record the annotation grade.** For an independently validated release, at least two annotators label every case independently, without seeing each other's decisions or retriever rankings. For the provisional pilot, one curator may record a resolved decision, explicitly without independent validation. Both inspect the same frozen metadata and candidate IDs. Record qualifications and domain experience; do not call either grade expert-verified unless qualified expert review actually occurred.
4. **Capture evidence.** For each accepted target, cite source metadata by source file digest, table/field locator and attribute (description, guidance, datatype, relationship, key, or other field). For Task B, cite the scope and examined plausible candidates. For Task C, cite every plausible candidate and the missing dimension.
5. **Record alternatives and rejections.** Accepted alternative field IDs are explicit. Record plausible rejected candidates and one or more reasons: wrong entity, grain, time role, population, semantic domain, identifier-vs-value role, unsupported interpretation, or other stated reason. Do not make the rationale depend on retriever rank.
6. **Adjudicate independent annotations.** A third reviewer reviews disagreements against source evidence and signs off the released set, recording decisions and rationale; cases may remain unresolved. A solo curator's resolution is not adjudication by an independent reviewer. Unresolved cases are excluded from scoring at either grade; preserve history rather than silently overwriting it.
7. **Audit task separation.** Re-check that every Task B case has no valid candidate and every Task C case has multiple plausible valid candidates plus a specific missing dimension. Record label changes as curator revisions or independent adjudications according to grade.
8. **Version the cases/gold.** Save protocol version, annotation grade, case IDs, curator/annotator decisions, review provenance and content digest. Never revise a published set in place; create a new version and document changes.

The retriever under evaluation must never generate its own supposedly independent gold labels.

### Engineering and release gates

- After B00 approval, B01–B04 engineering checks can run on clearly synthetic fixtures and resolved provisional curator cases. Provisional experiments must state their grade in inputs, manifests and results, remain separate from independently validated results, and make no independent/expert verification claim.
- A separately versioned provisional pilot may be shared as such after source/redistribution checks. The 100-case count is a target, not an engineering prerequisite or proof of validation.
- Publishing an **independently validated gold benchmark** or results under that designation requires two independent annotations per case, third-reviewer adjudication/sign-off, no unresolved scored labels, frozen splits, provenance and rights checks. Engineering completion alone does not satisfy this release gate.

## Split and leakage controls

- Before split assignment, create groups linking paraphrases of the same requirement, the same normalized business concept, near-identical accepted-target families, same authoring template family, and all variants generated from one seed/template. A group cannot cross partitions.
- Keep synonym transformations, templated wording, and derived variants of a prompt in one group. Do not author one paraphrase for train and a near-copy for test.
- Group related near-duplicate target cases together where feasible; all alternatives for a case stay in one group. Candidate metadata may appear in every run because it is the fixed estate; query text or labels from another partition may not.
- Use a recorded deterministic grouped, stratified **60/20/20 train/validation/test** assignment for the 100-case target, with a recorded seed and split manifest. The pilot can be used to refine instructions, but it must not be reused as a hidden test set after retriever-driven iteration.
- If category constraints make the requested proportions impossible without splitting a group, preserve group integrity, record actual counts, and report them. Do not force leakage to hit a target percentage.
- Any model/index fitting, no-match threshold choice, clarification threshold choice, or parameter selection uses train/validation only. Freeze these settings before test evaluation.

## Evaluation protocol and denominators

Let `E = A union B union C` be the full adjudicated evaluation partition after any explicitly recorded eligibility exclusions; `A`, `B`, and `C` are its mutually exclusive task labels, and `A_original` is Task A before those exclusions. No class-based filtering is permitted for classification metrics. Report original/included/excluded case IDs, exclusion reasons and every class support count. Provisional experiments apply the same formulas to their curator-resolved set but label the grade and never combine it with adjudicated gold. For Task A case `i`, let `G_i` be its accepted alternative field IDs and `R_i` its ranked results, ordered by descending raw score then canonical `FieldId` ascending. This deterministic ID tie-break makes output stable; tied scores are not evidence of equal correctness probability.

| Metric | Definition and denominator |
|---|---|
| Top-1 exact table-column accuracy | `sum(1[R_i[1] in G_i]) / count(A)`. Empty rankings count incorrect. “Exact” means the returned field ID exactly matches an accepted ID, including its namespace/table. |
| Recall@K (case hit rate; report K=5) | `sum(1[set(first K entries of R_i) intersects G_i]) / count(A)`. Alternative accepted IDs are OR alternatives; returning any one in the first K is a hit. |
| MRR | `sum(1 / rank_i) / count(A)`, where `rank_i` is the first rank whose field ID is in `G_i`; zero if none is retrieved. |
| Candidate-universe coverage audit | Before scoring/exclusions, `sum(1[G_i intersects U_i]) / count(A_original)`, where `U_i` is the full eligible universe. This measures whether any acceptable alternative is eligible, regardless of ranking; also report every out-of-universe gold reference and affected case, including partially eligible alternative sets. Such references must fail validation or cause explicit case exclusions. Coverage on a nonempty validated scored `A` is therefore 100%; the audit is not Recall@K and missing eligibility is not scored as a ranking miss. |
| No-match detection | One-versus-rest precision, recall and F1 for `NO_MATCH` over **all of E**, using the counts below, including false positives on both A and C. |
| Clarification detection | One-versus-rest precision, recall and F1 for `NEEDS_CLARIFICATION` over **all of E**, including false positives on both A and B. |

For each class `X` in `{NO_MATCH, NEEDS_CLARIFICATION}`, define `y_i` as its adjudicated label and `p_i` as the separate decision rule's predicted label:

- `TP_X = count(i in E: y_i = X and p_i = X)`.
- `FP_X = count(i in E: y_i != X and p_i = X)`; either other true class contributes false positives.
- `FN_X = count(i in E: y_i = X and p_i != X)`; either other predicted class contributes false negatives.
- `precision_X = TP_X / (TP_X + FP_X)`; `recall_X = TP_X / (TP_X + FN_X)`; `F1_X = 2*TP_X / (2*TP_X + FP_X + FN_X)`.

When a formula's denominator is zero, emit `null`/not applicable for that metric and report the counts; never silently substitute 0 or 1. F1 is 0 when its denominator is positive and TP is 0. Ranking metrics and the coverage audit are likewise not applicable when their case denominator is zero. A classification run must supply exactly one of `DIRECT / NO_MATCH / NEEDS_CLARIFICATION` for every case in E; missing/invalid predictions fail validation. If classification is not run, mark its metrics **not evaluated**, rather than treating absent decisions as a label. Include the full three-way confusion matrix whenever classification is evaluated; optional three-way accuracy is secondary. Never combine B and C into a generic abstain class.

Eligible fields omitted from an index are an index-validation failure. A truncated ranked list is allowed: failing to retrieve eligible gold in its first K results is a normal Recall@K miss. Eligibility and exclusions must be identical for all compared methods.

### Thresholds, ties and score interpretation

- Retrieval returns ranked field IDs and raw method scores. No BM25, vector cosine or RRF score is a calibrated probability.
- B03's required BM25 baseline supplies rankings and Task A retrieval metrics; outcome classification is a separate, optional experiment. Empty/low-score rankings do not establish no-match, and close/tied scores do not establish semantic ambiguity. No reliable B/C detection is promised from uncalibrated scores.
- If experimental classification heuristics are included, give each an explicit rule ID/version, input features, parameters, label mapping and conflict/tie handling, separate from BM25 ranking. Label results experimental and evaluate all three classes over E in a separate classification report. Tune thresholds only on train/validation and freeze before test; report sweeps separately. With no explicit rule, classification remains not evaluated.
- Stable serialization sorts exact score ties by canonical field ID ascending. This tie rule is applied before all rank metrics and saved in the experiment manifest.
- Every method and ablation uses the same snapshot, eligibility policy, case IDs, split, and full candidate universe. A method may return fewer top results, but its index cannot drop candidates silently.

## Latency, reproducibility and outputs

Record index-build time separately from query latency. Measure per-case query latency with a monotonic clock; publish median and p95 for the evaluated split, warm/cold state, number of cases, candidate count, device/CPU/GPU, thread count, Python and OS versions. Do not set a pass threshold in B00.

Each run preserves:

- per-case verbatim requirement, task label (evaluation only), gold IDs, prediction/outcome, ranked candidates, raw scores, ranks, evidence, decision rationale and latency;
- aggregate metrics with explicit denominators and excluded-case reasons;
- source snapshot and file digests, dataset and case/gold versions/digests, annotation grade, split manifest and seed, and the research corpus reference/digest once supplied under the [research provenance policy](../plans/b00-b04-implementation.md#research-corpus-provenance-and-versioning);
- Git revision/dirty state, Python/dependency lock, method and serializer versions, ablation profile, model ID/revision/weight digest when applicable, hardware/runtime settings, and UTC run timestamp.

Use canonical JSON/JSONL serialization for results, manifest and metrics. Runtime observations remain variable: latency, build times and UTC timestamps are not expected to be byte-identical. Reproducibility compares snapshot/document/case/split/universe digests and the static configuration/provenance fields, then the canonical per-case projection of IDs, candidate order, raw scores, evidence and any explicit outcome decisions, plus non-timing metrics. Exclude runtime observations and incidental run/output locations from equality checks; mixed artifacts such as `cases.jsonl` and `run.json` are not compared wholesale. Under a fixed supported environment, BM25/RRF ordering and deterministic serialization must match. B04 must declare any dense-score numerical tolerance and runtime limitations in advance, still checking candidate order and reporting rank changes. Keep identifiers and evidence references so a reviewer can reconstruct why a candidate appeared.

## Planned metadata ablations

Use the same field IDs and candidate universe for:

1. table and field names only;
2. names plus field-level description/guidance;
3. the preceding text plus table description/guidance.

Record missing-channel counts for each profile. Do not compare an ablation that silently changes which candidate fields are indexed. Relationships/keys may be reported as a later ablation after a separate design review.

## Limitations

The target set is small and standard-specific. Scores describe these snapshots, tasks, annotators and splits; they are not universal enterprise binding performance. Report category-level counts and uncertainty, preserve all per-case outputs, and avoid over-interpreting differences when denominators are small.
