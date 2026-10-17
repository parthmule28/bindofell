# Benchmark annotation protocol

This is the B02 annotation workflow for the approved
[benchmark specification](../design/0002-benchmark-v0.1.md). The committed
[toy fixtures](../../tests/fixtures/benchmark/README.md) are deliberately
synthetic engineering examples. They are neither OMOP gold nor independent or
expert verification. No real pilot has been curated by this implementation.

## Freeze before authoring

1. Acquire OMOP CDM **v5.5.0**, revision
   `ba3dc1b651cc243279052bca3d051485c3ec1136`, using the
   [B01 local procedure](../usage/b01-metadata.md#local-acquisition-and-real-source-check).
   Retain the actual source SHA-256 manifest and imported snapshot. Never
   substitute counts or hashes from a different acquisition.
2. Declare one eligible physical-field universe, eligibility rule ID/version
   and configuration. Keep it method independent. Normally include all physical
   fields; exclusions require a stated metadata policy. Save its canonical digest.
3. Assign protocol, case-set and gold versions. Record the author, authoring
   basis and verbatim business requirement. Write requirements without querying
   the evaluated retriever or viewing its scores, rankings or predictions.
4. Keep upstream source files local. The pinned upstream `DESCRIPTION` declares
   Apache License 2.0; component notices and redistribution obligations still
   require review before copying descriptions or bundling source material.
   Public availability does not grant unrestricted redistribution.

## A feasible 15–20-case provisional pilot

A named solo curator may author **15–20 provisional cases** to try the rubric
before expanding. Aim to exercise straightforward targets, independently worded
synonyms, repeated field names, bounded absences and missing business dimensions;
these are coverage goals, not quotas to satisfy by inventing evidence. Inspect
source descriptions/guidance, types, keys and relationships. Preserve absent
metadata. If evidence cannot support a decision, keep the case unresolved.

Record actual curator identity, qualifications and domain experience, including
"none claimed" when appropriate. `provisional_curator` requires one curator
annotation and no third-party adjudication record. It makes no independent or
expert verification claim. A resolved curator decision supports separately
labeled engineering experiments. Do not call a solo resolution adjudication.

The eventual 100-case plan and 60/20/20 proportions remain targets. Completing
B02 does not require a real pilot, 100 labels, or any measured retrieval score.

## Task decision rubric

| Label | Required annotation | Common rejection reasons |
|---|---|---|
| `direct` (A) | At least one exact field ID; accepted IDs are OR alternatives, with source evidence for every alternative | Wrong entity, grain, date role, population, semantic domain, or identifier versus value |
| `no_match` (B) | No accepted/plausible target; explicit scope of the frozen eligible estate, rationale, examined candidates and rejection reasons when applicable | A related field does not directly represent the requested concept; a required formula is outside the direct track |
| `needs_clarification` (C) | At least two distinct plausible field IDs, a rationale for each interpretation, and the specific missing business dimension | Prompt does not select event/entity, date role, population or grain |

Every gold record has an overall rationale and source evidence. Evidence retains
its original locator, attribute/value, asset ID and source digest. Every accepted,
plausible or rejected field needs source evidence attributed to that exact asset.
For B, cite the inspected scope even when no plausible rejected field exists.
Record rejections in `rejected_candidates`; do not use rank or score as a reason.

Multiple accepted A IDs mean **any one is a correct direct answer**. If multiple
fields must be combined simultaneously, retain the case for a future derived
track; do not label it an OR mapping. C requires interpretations in addition to
plausible IDs, so a curator must state how the meanings differ. Retrieval failure
cannot establish B, and score ties cannot establish C.

## Independent validation and release gate

To release cases or results as `independently_validated`:

1. At least two distinct annotators inspect the frozen metadata independently,
   without seeing each other's decisions or retriever outputs. Retain each
   original annotation reference, complete `mapping` decision, rationale and
   contributor details. Preserve exact accepted/rejected field IDs, C
   interpretations/missing dimension or B scope, and evidence for each annotator;
   agreement on A/B/C alone is insufficient.
2. A distinct third adjudicator reviews disagreements against evidence and
   signs off the final label/rationale and the complete final gold `mapping`. Record dissent and unresolved cases;
   do not overwrite original annotations with the resolution.
3. Re-audit alternatives, B scope, C interpretations and source rights. Freeze
   case/gold/protocol versions, content digest, universe and splits.
4. Publish only resolved cases in a scored partition. Label qualifications
   accurately; independent review alone is not proof of clinical expertise.

The code checks recorded role IDs, independence flags, sign-off and label
and mapping consistency. Independently validated cases use case schema `1.1`;
see the [migration rules](../usage/b02-benchmark.md#review-mapping-records-and-migration).
It cannot verify that people actually worked independently, that
identities are truthful, or that a semantic judgment is correct. Unresolved
records may be archived but are rejected from scoring. A grade requesting
independent validation may retain unresolved review history; that is not a
validated release. Promotion of a curator case requires the full gate again.
Never invent reviewers. Provisional and validated cases cannot share a headline
aggregate. Synthetic independent-role records in unit tests only test this gate.

## Split and revision discipline

Assign a `split_group_id` before partitioning. Declare links for shared concepts,
paraphrase families, seeds, templates and related target families. Every declared
family must have the same group across all its variants, and every group stays
within one partition. Manually inspect for undeclared semantic relationships;
the code cannot discover them from wording.

Save the seed and algorithm version with actual group/case/class counts. Tiny
corpora need not achieve 60/20/20. The versioned grouped greedy assignment
balances class and total counts while preserving groups; it is not a guarantee
of an optimal stratification. Inspect actual distributions before release.

Tune future retrieval/decision settings on train/validation only. A pilot used
to refine instructions must not later become a hidden test set. A published
change creates new case/gold versions, retains original evidence and annotations,
and records the revision rationale. A breaking JSON contract change requires a
schema version increment and migration note.

## Engineering acceptance versus released gold

Synthetic and resolved provisional cases can verify contracts, splits, metrics
and output provenance. They establish neither search quality nor domain accuracy.
An independently validated release additionally needs the human review, rights
and freeze gates above. See [B02 formats and metrics](../usage/b02-benchmark.md)
for exact input validation and a fully offline supplied-ranking example.

The reported 50-paper research ledger is still unavailable. No research records
are reconstructed here; use the existing
[research provenance policy](../plans/b00-b04-implementation.md#research-corpus-provenance-and-versioning)
when its real immutable export or repository revision is supplied.
