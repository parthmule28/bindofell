# B02 benchmark and supplied-ranking evaluation

B02 supplies offline contracts, validation, grouped splits and metrics. It does
not run a retriever or infer truth labels from scores. [B03](cli.md) composes
local BM25 with this evaluator. The
[annotation protocol](../benchmark/annotation-protocol.md) defines human curation
and the independent validation gate. All committed examples are synthetic and
marked `provisional_curator`; no real OMOP pilot or expert gold is included.

## Run the synthetic example

Run from the repository root after `uv sync --locked --all-groups`:

```python
from pathlib import Path

from bindofell.benchmark.io import load_cases, make_universe
from bindofell.benchmark.splits import assign_splits, manifest_to_json
from bindofell.evaluation.contracts import MethodSpec
from bindofell.evaluation.runner import (
    case_results_to_jsonl,
    evaluate_supplied,
    load_rankings,
    result_to_json,
)
from bindofell.metadata.loader import load_snapshot

fixtures = Path("tests/fixtures/benchmark")
snapshot = load_snapshot(fixtures / "toy_estate.json")
universe = make_universe(snapshot)
cases = load_cases(fixtures / "toy_cases.jsonl", snapshot, universe)
splits = assign_splits(cases, seed=17)
rankings = load_rankings(fixtures / "toy_rankings.jsonl")
method = MethodSpec(
    method_id="toy-supplied/1",
    version="1",
    config={},
    indexed_field_ids=universe.field_ids,
    universe_digest=universe.digest,
)
result = evaluate_supplied(
    snapshot, cases, universe, rankings, method=method, split_manifest=splits
)
print(result.direct.model_dump())
print(result.classification.status)  # not_evaluated
# Canonical artifacts; save to new versioned paths when retaining results.
static_report = result_to_json(result)
case_records = case_results_to_jsonl(result)
split_record = manifest_to_json(splits)
```

The deliberately constructed rankings give the one synthetic A case a hit at
rank 1: support 1, Top-1/Recall@5/MRR all 1. These are **fixture assertions**,
not retrieval performance. B has an empty ranking; C has tied candidates, and
neither produces an outcome decision. To evaluate a single partition, pass
`partition="test"` and supply rankings/decisions for exactly that partition.

## JSONL case and gold format

Each line is one `EvaluationCase` from `bindofell.benchmark.models`:

| Fields | Meaning |
|---|---|
| `schema_version`, `case_version`, `case_id`, `snapshot_id` | Case serialization `1.1` (legacy provisional `1.0` readable), independently versioned case corpus and immutable identities |
| `requirement` | B01 `BusinessRequirement`, including verbatim text and explicit context |
| `task_label`, `split_group_id`, `family_links` | A/B/C truth plus declared leakage groups; family kind and namespaced family ID |
| `protocol_version`, `author_id`, `authoring_basis` | Original human authoring context and protocol reference |
| `annotation_grade`, `review_state`, `annotations`, `adjudication` | Named contributors, original annotation references, decisions, independence and sign-off |
| `gold` | `GroundTruthMapping`: schema `1.0`, gold version, label, accepted/plausible IDs, interpretations, missing dimension, scope, rationale, rejections and source evidence |

See the complete [toy JSONL](../../tests/fixtures/benchmark/toy_cases.jsonl).
`accepted_field_ids` and `plausible_field_ids` reject duplicates and serialize
sorted. `interpretations` and `rejected_candidates` contain `field_id` plus
`rationale`. Every referenced target/rejection needs a source-kind B01 `Evidence`
whose `asset_id` is that exact field. B additionally needs `scope`; C needs two
distinct plausible IDs and `missing_dimension`. Task-incompatible gold fails.

Generate authoritative JSON Schemas from the owning models:

```sh
uv run python -c 'import json; from bindofell.benchmark.models import EvaluationCase; print(json.dumps(EvaluationCase.model_json_schema(), indent=2))'
uv run python -c 'import json; from bindofell.evaluation.contracts import CaseRanking; print(json.dumps(CaseRanking.model_json_schema(), indent=2))'
```

`load_cases`/`cases_from_jsonl` and `cases_to_jsonl` perform strict versioned
loading/canonical export. Unsupported versions, extra fields, duplicate keys or
case IDs, non-finite numbers (including overflow), malformed UTF-8 and blank
records fail with source/line context and case ID when available. Unresolved
records can be loaded for review but cannot be scored. Errors identify all
invalid target IDs in the affected case. Case order is canonical by `case_id`.

## Review mapping records and migration

Case schema **`1.1`** adds each annotation's `mapping`, reusing the sole
`GroundTruthMapping` contract (gold schema remains `1.0`). Every annotator records
their own accepted OR fields, rejected candidates, plausible interpretations,
missing dimension or no-match scope, rationale and evidence, even when two
annotators agree on the A/B/C label. These original decisions are preserved;
they need not agree with each other or the final gold.

An adjudicator's `mapping` must equal the complete final gold for a resolved
case, including field IDs, rejections, interpretations, evidence and gold version.
Its separate rationale explains the resolution. Sign-off and distinct-reviewer
requirements still apply. Each annotation/adjudication label must match its own
mapping label.

Existing provisional `1.0` cases remain readable. Independently validated cases
must use `1.1`; label-only reviews cannot prove review of field mappings.
Migration requires the **actual original decisions** from annotation records,
not copying final gold into both annotators' records. Add the adjudicator's actual
final mapping/sign-off, set case schema to `1.1`, increment the case corpus
version and regenerate case digests and splits. New `1.1` provisional records
also require their curator's mapping, which must match final gold when resolved.
No historical decisions are inferred.

## Candidate universe and gold integrity

`make_universe(snapshot)` selects all physical fields. A subset requires explicit
`field_ids` and a documented eligibility `rule_id`/`rule_version`/`rule_config`.
`EligibleUniverse.digest` hashes canonical JSON of snapshot ID, policy and sorted
IDs. Persist that record and digest unchanged across all compared methods.
`MethodSpec.indexed_field_ids` must equal the full eligible set. A truncated
ranking is allowed; omitting an eligible field from the index is a validation
failure.

Gold source evidence is checked for every final, annotator and adjudicator
mapping. Source asset IDs must resolve to the snapshot, dataset, table, field or
relationship; source digests must belong to the snapshot's manifest. Rejected
field IDs must exist in the snapshot (they may be ineligible for a documented
reason), and accepted/plausible IDs must also be eligible.

Where original source evidence records are available, an existing evidence ID
is immutable. A new evidence ID must still match the asset's original source
digest, locator, attribute and value, or a nonempty verbatim text excerpt.
Excerpts require a new ID; retaining an original ID while changing its contents
fails. Inventing a new ID cannot bypass these checks. When an asset has no
original source records, the named scalar attribute must exist in its raw
attributes or canonical metadata and the value must match (or be a verbatim
text excerpt). Missing metadata cannot be replaced with an invented description.
Without original records the exact locator cannot be independently verified;
the checker verifies available snapshot content and manifest membership, not
external source bytes or human correctness. Errors include case, review decision
and source evidence ID, plus file/line when loaded from JSONL.

Every accepted A alternative and plausible C field must exist in the snapshot
and eligible universe, including partially eligible OR lists. This implementation
**fails closed**; it does not implement automatic eligibility exclusions. Correct
the input or publish a separately reviewed case/universe revision. Do not remove
one alternative, relabel B, or score ineligible gold as a miss. Resolved included
cases must share one annotation grade.

`coverage_audit(cases, snapshot, universe)` can inspect original A annotations
before scoring: it returns support, count/rate with any eligible alternative and
every missing/ineligible reference. A partially eligible OR case can have
coverage 1 while still failing integrity. Coverage is unrelated to rank and is
not Recall@5. Valid nonempty scored A has coverage 1 with no integrity issues.

## Split manifest

`assign_splits(cases, seed=...)` uses
`bindofell.grouped-stratified-greedy/1`. It orders groups by size, class rarity,
then seeded SHA-256; each assignment minimizes marginal squared error against
60/20/20 class and total case counts. Partition order breaks remaining cost ties.
It preserves group integrity over target proportions and records actual group,
case and A/B/C counts for each partition. It does not infer semantic families.

`SplitManifest` has schema, algorithm version, seed, cases digest, assignments
(case ID/group/partition) and counts. `manifest_from_json(text, cases)` validates
exact case coverage, family cohesion, group integrity, actual counts and replay
of the recorded algorithm/seed. No case/group may cross train/validation/test.
The evaluator validates the whole manifest before selecting a partition.

## Supplied rankings and optional decisions

Each `CaseRanking` JSONL line contains `schema_version="1.0"`, `case_id`,
`snapshot_id` and `candidates` (B01 `BindingCandidate` records). See
[toy rankings](../../tests/fixtures/benchmark/toy_rankings.jsonl).
Empty and truncated candidate lists are valid. Supplied ranks must be unique and
contiguous from 1; field IDs must be unique. The contract canonically orders by
**descending raw score, then ascending full field ID**, and assigns ranks to that
order. Input array order and supplied tie ranks do not control metric ranks.
Raw scores and evidence are preserved; scores are not probabilities.

The evaluator requires exactly one ranking for every included case, including
empty lists. Every candidate must match its case's requirement, snapshot,
eligibility universe and declared method/config. `MethodSpec` records method ID,
version, scalar configuration, full indexed field IDs and universe digest.

Classification is a separately configured experiment. To evaluate it, pass an
`OutcomeRule` (ID/version/config, named input features and description) and one
`OutcomeDecision` for **every** included A/B/C case. Each decision records schema,
case/snapshot, rule ID/version, uppercase `DIRECT`, `NO_MATCH` or
`NEEDS_CLARIFICATION`, rationale, input reference and optional evidence. B02
accepts supplied decisions; it contains no rule execution or classifier heuristic.
Missing, extra, duplicate or mismatched decisions fail. With no rule,
classification is `not_evaluated` and its metric records are absent. Never choose
thresholds using test labels.

## Exact metric definitions

For included resolved A cases with OR gold set `G` and canonical ranked list `R`:

- **Top-1:** cases with `R[0]` in `G` divided by A support.
- **Recall@5:** cases with any accepted alternative among the first five divided
  by A support. It does not require retrieving every alternative.
- **MRR:** sum of reciprocal first matching ranks divided by A support. A match
  at rank 6 contributes `1/6` to the numerator and no Recall@5 hit.
- Empty rankings and valid misses contribute zero. Empty A produces `null`
  rates with support 0. Counts and reciprocal-rank sum are retained.

Optional classification evaluates full included **E = A ∪ B ∪ C**. For each
class X (the report includes all three, with B/C distinct):

- TP: true X, predicted X.
- FP: predicted X, true **either other class**.
- FN: true X, predicted **either other class**.
- Precision `TP/(TP+FP)`, recall `TP/(TP+FN)`,
  F1 `2*TP/(2*TP+FP+FN)`.

Every zero denominator yields `null`, with raw TP/FP/FN and support. A positive
F1 denominator with TP 0 yields 0. The complete 3×3 confusion matrix is retained;
B→C and C→B errors count in both affected one-versus-rest reports.

## Static artifacts and limitations

`result_to_json` includes canonical case-level records, aggregate metrics,
original/included IDs (equal here; exclusions are not implemented), empty
excluded IDs, A/B/C supports and static provenance. Each case record embeds the
complete case/gold, canonical supplied ranking, first match and optional decision.
Provenance retains source-file hashes, snapshot content digest, case digest,
full universe/policy/digest, full split manifest/digest, selected partition,
method/config and annotation grade. `case_results_to_jsonl` writes the ordered
case projection. No independent grades are mixed in one aggregate.

Snapshot hashing excludes only `dataset.retrieved_at`; source and content changes
still change the digest. B02 artifacts contain no runtime timestamps or latency,
so compare report JSON, case JSONL, split/universe records and digests byte for
byte for identical static inputs. B03 owns the future runtime manifest. Its
variable latency/timestamps must be excluded from these comparisons. Evidence
or annotation changes are static content changes, not ignored observations.

Code enforces structural/provenance assertions, not the truth of human judgments
or index declarations. Declared group links need human semantic review. The toy
scores say nothing about OMOP accuracy. Component licensing and the unavailable
research ledger retain the limitations documented in B00/B01.

## Verification and CI

```sh
uv sync --locked --all-groups
uv run pytest tests/unit -q -W error
uv run ruff check
uv run pyright
git diff --check
```

The [PR workflow](../../.github/workflows/ci.yml) installs locked dependencies,
then runs offline unit tests with warnings as errors, Ruff and strict Pyright
on Python 3.11. Checkout fetches full history; the whitespace step checks the
committed PR merge-base-to-head diff using the event's base/head SHAs. Main
pushes use before/head SHAs, with an empty-tree check on an initial push.
Missing commits fail the check; uncommitted changes do not affect it.
Test sockets are blocked. It acquires no OMOP source or model
weights. B02 stops at independent PR review before B03.
