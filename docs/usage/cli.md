# B03 lexical CLI and reproducible experiments

B03 connects the [B01 metadata](b01-metadata.md) and
[B02 benchmark/evaluation](b02-benchmark.md) contracts through local BM25.
It does not create gold, approve mappings, classify no-match/clarification,
or implement B04 dense/hybrid retrieval. Scores are raw lexical ranking signals,
not probabilities. Both commands work offline after locked dependency setup.

## Install and verify

Requires Python 3.11+ and uv. From the repository root:

```sh
uv sync --locked --all-groups
uv run bindofell --help
uv run python -m bindofell --help
uv run pytest tests/unit tests/integration -q -W error
uv run ruff check
uv run pyright
git diff --check
```

Both entry points call the same argparse implementation. `bm25s[indexing]` is
pinned to **0.3.13**. Its NumPy/SciPy indexing dependencies and development tools
are locked in `uv.lock`, including separate Python 3.11 and 3.12+ compatible
resolutions. The installed bm25s distribution declares MIT; installed scientific
wheels contain their own licenses/notices. No source CSVs or model weights are
bundled. No stemming, model, hosted search or optional JIT extras are enabled.

## Search

```sh
uv run bindofell search --estate tests/fixtures/benchmark/toy_estate.json \
  --requirement "Alpha key" --profile names --top-k 5
```

Canonical JSON is printed to the console. Add `--output NEW_FILE` to save the
same UTF-8 JSON instead. Its parent directory must exist; an existing file is
never overwritten. Each hit includes the B01 `BindingCandidate` (rank, full field
ID, raw score, method/config and evidence), complete `FieldAddress`, and selected
`SearchDocument` channels with source-evidence IDs. Explicit catalog/schema slots
preserve qualified-address distinctions. Method, tokenizer, serializer, source
hashes, universe and document/token digests accompany the results.

Ad hoc requirement IDs use `urn:bindofell:requirement:sha256:` followed by SHA-256
of the **verbatim UTF-8 request text**, including whitespace; identity hashing
performs no normalization. Search tokenization is separate. Empty/whitespace or
punctuation-only queries yield an empty result, not a `NO_MATCH` prediction.
Unseen tokens give zero-score candidates, ordered deterministically. A positive
`--top-k` limits display only and may exceed the number of eligible fields.

Profiles reuse the existing B01 channel selection:

| Profile | Indexed channel values |
|---|---|
| `names` | Table name and field name |
| `field_descriptions` | Names plus available field description/guidance |
| `table_context` | Preceding channels plus available table description/guidance |

Only channel **values** are tokenized; channel-label strings are not indexed.
Source terminology, descriptions and missing metadata remain unchanged. No
class words, types or descriptions are inferred from names. Omitted channels
are recorded. Every profile retains the same complete eligible field universe,
including sparse or tokenless documents. Supplying custom documents to the
Python index API requires exact agreement with B01's snapshot/profile output.

The default universe is all physical fields. `--universe PATH` accepts a frozen
B02 `EligibleUniverse` JSON record for an explicitly documented metadata policy.
Unknown fields, wrong snapshots, duplicated/missing documents or altered channel
content fail validation. The method's indexed IDs must equal that full universe;
zero-score fields are never silently excluded.

## Tokenizer and scoring specification

Tokenizer **`bindofell.nfkc-casefold-words/1`** applies Unicode NFKC, splits
Unicode lower-to-upper camel boundaries, acronym-to-word boundaries and
letter/digit transitions, then casefolds each token. Letters/numbers form words;
combining marks stay with an existing word. Underscores, dots, whitespace and
punctuation are separators. For example:

```text
person_id Alpha.key bloodPressure -> person id alpha key blood pressure
HTTPServer BP2 mmHg               -> http server bp 2 mm hg
StraßeDate ＣＡＦÉ café             -> strasse date café café
```

There is no abbreviation expansion, stemming, stopword removal or semantic
normalization. Tokenizer/Unicode versions and token digest are recorded.

Scoring uses the pinned bm25s **Lucene** variant and IDF, `k1=1.5`, `b=0.75`,
`delta=0.5` (unused by the Lucene variant), NumPy scoring/CSC backends,
`float64` scores, `int32` index integers and no auto-compilation. The library's
empty-token facility is enabled. These exact arguments are saved in
`MethodSpec.config`; do not assume another BM25 package produces the same scale.
All-tokenless corpora return finite zero scores while retaining every field.
Ordering is descending raw score, then ascending complete canonical field ID.
Ranks are contiguous from 1. Source/channel evidence is copied only when actually
present; conflicting contents under one evidence ID fail before indexing. Generated computation evidence separately identifies the method,
configuration, request/field IDs, document/query digests and raw score.

## Evaluate with explicit split policy

Exploratory smoke run, generating and saving grouped splits:

```sh
mkdir -p .data/b03-smoke
uv run bindofell evaluate --estate tests/fixtures/benchmark/toy_estate.json \
  --cases tests/fixtures/benchmark/toy_cases.jsonl --split all --seed 17 \
  --profile names --output-dir .data/b03-smoke/run-a
```

Replay that frozen assignment with a selected partition:

```sh
uv run bindofell evaluate --estate tests/fixtures/benchmark/toy_estate.json \
  --cases tests/fixtures/benchmark/toy_cases.jsonl --split test \
  --split-manifest .data/b03-smoke/run-a/split.json --profile names \
  --output-dir .data/b03-smoke/test-replay
```

Choose **exactly one** of `--split-manifest PATH` or `--seed INTEGER`. Nothing
silently generates a published test split. Generated splits are explicitly
exploratory. `--split all` combines partitions and is always exploratory, even
with a frozen manifest; it is not a publishable held-out test result. Replayed
manifests validate original case digest, groups/families, counts, algorithm and
seed. Freeze future settings on train/validation before test; this CLI performs
no parameter or threshold tuning.

Benchmark snapshot/universe, source evidence, split integrity and included
review-state/grade checks run before indexing. Every included A/B/C case gets a
ranking. The retriever receives only snapshot documents, requirement text and
identity; labels, accepted/rejected targets, review rationales and split labels
never enter its scoring API. B02 `evaluate_supplied` alone computes the metrics.

Evaluation ranks **all eligible fields**, regardless of search's `--top-k`.
Thus B02's MRR is unrestricted over the produced ranking, not MRR@5. Rank 6
contributes `1/6` to MRR and no Recall@5 hit. Unusable query text explicitly
returns an empty ranking and counts as a miss on A. The manifest rejects
truncated nonempty-query rankings marked as unrestricted MRR. Top-1 and
Recall@5 use B02 case-hit denominators and OR alternatives; empty A produces
`null` rates with support 0. Classification is always `not_evaluated`: B/C truth
labels remain intact and neither empty nor tied rankings produce decisions.

## Artifacts and publication policy

`--output-dir` must name a **new directory** under an existing parent. Existing
directories/files/symlinks are rejected. Inputs, evaluation and serialization
finish before publication; files are staged, a directory is exclusively reserved,
and `run.json` is published last. Invalid inputs produce no success directory.
Mismatched report/manifest pairs fail before publication.
I/O failures clean this writer's new artifacts without deleting unrelated data.
This is not a promise that all files become visible simultaneously to concurrent
readers; treat the final `run.json` as the completion record.

| Artifact | Owner and contents |
|---|---|
| `metrics.json` | Full B02 `EvaluationResult`: authoritative metrics/counts/nulls, grade, provenance and case records |
| `cases.jsonl` | B02 `CaseEvaluation` projection: verbatim requirement, separate gold and actual full rankings/scores/evidence |
| `run.json` | B03 `RunManifest`: static inputs/results and separate runtime observations |
| `split.json` | Frozen B02 `SplitManifest`, directly reusable by `--split-manifest` |
| `universe.json` | B02 `EligibleUniverse`, directly reusable by `--universe` |

The complete B02 result in `metrics.json` intentionally also preserves its case
records; the JSONL is the convenient case-level projection. No second metric
formula or domain-contract hierarchy is introduced.

## Manifest and reproducibility

`RunManifest` schema `1.0` separates:

- **Static:** B02 `StaticProvenance` with source snapshot/version/revision/hashes,
  timestamp-excluded snapshot digest, complete universe/policy/count/digest,
  full splits/seed/partition; case/gold/protocol versions/grade and digests;
  document/token/result digests, profile/serializer/tokenizer, omitted channels,
  exact BM25 configuration, software versions, Git revision/dirty state and lock
  SHA-256. Research provenance explicitly remains `unavailable`.
- **Observations:** aware UTC timestamp, monotonic index-build duration and
  per-case retrieval durations; median and p95 using nearest rank
  `ceil(0.95*n)` (null on no queries); warm/cold protocol, OS/machine/CPU and
  available thread environment settings. Missing hardware values remain null.

Index duration includes document/token preparation and BM25 construction. Query
duration includes scoring, deterministic ordering and candidate/evidence
construction; it excludes evaluation and output I/O. The index is built once;
queries execute sequentially, the first query is unwarmed and caches are not
flushed. No latency pass threshold is claimed.

Git/lock provenance is captured from a verified editable source layout, not an
unrelated data working directory. If source Git metadata or lock bytes cannot
be obtained (for example an installed wheel), they are explicitly unavailable.
Actual installed package and Python versions are retained. Dirty state includes
untracked, non-ignored files; keep experimental output in ignored `.data/` so
output creation does not change the source-state declaration between runs.

`static_projection(manifest)` excludes observations and incidental paths;
`static_digest` hashes that projection. Compare document/token digests, method
configuration, canonical candidate IDs/order/raw scores/evidence, B02 non-timing
metrics and static provenance. Timestamps, latencies and host-dependent values
are not byte-equality targets. Snapshot hashing excludes acquisition timestamp.
Scores use full precision JSON serialization. Reproducibility is checked in a
fixed supported environment; Python/Unicode/scientific-wheel versions are
recorded and cross-platform numerical identity is not asserted.

## Repeat the engineering smoke twice

The committed [toy fixture](../../tests/fixtures/benchmark/README.md) has **two
fictional tables, eight fields and three provisional A/B/C cases**. Run the
previous exploratory evaluation once as `run-a`, then:

```sh
uv run python -m bindofell evaluate --estate tests/fixtures/benchmark/toy_estate.json \
  --cases tests/fixtures/benchmark/toy_cases.jsonl --split all --seed 17 \
  --profile names --output-dir .data/b03-smoke/run-b
uv run bindofell search --estate tests/fixtures/benchmark/toy_estate.json \
  --requirement "Alpha key" --profile names --top-k 5 \
  --output .data/b03-smoke/search-a.json
uv run python -m bindofell search --estate tests/fixtures/benchmark/toy_estate.json \
  --requirement "Alpha key" --profile names --top-k 5 \
  --output .data/b03-smoke/search-b.json
```

Verify owning models and the static projections:

```python
from pathlib import Path

from bindofell.benchmark.io import strict_object
from bindofell.cli import SearchOutput
from bindofell.evaluation.contracts import CaseEvaluation, EvaluationResult
from bindofell.experiments.manifest import manifest_from_json, static_projection

root = Path(".data/b03-smoke")
assert (root / "search-a.json").read_bytes() == (root / "search-b.json").read_bytes()
SearchOutput.model_validate(strict_object((root / "search-a.json").read_text()))
for name in ("run-a", "run-b"):
    EvaluationResult.model_validate(strict_object((root / name / "metrics.json").read_text()))
    for line in (root / name / "cases.jsonl").read_text().split("\n"):
        if line:
            CaseEvaluation.model_validate(strict_object(line))
for filename in ("metrics.json", "cases.jsonl", "split.json", "universe.json"):
    assert (root / "run-a" / filename).read_bytes() == (root / "run-b" / filename).read_bytes()
a = manifest_from_json((root / "run-a/run.json").read_text())
b = manifest_from_json((root / "run-b/run.json").read_text())
assert static_projection(a) == static_projection(b)
```

For the `names` fixture run, A support is 1, Top-1 is 0, Recall@5 is 1 and MRR is
0.5. These are **engineering smoke assertions**, not real retrieval accuracy.
No real OMOP business cases, independent/expert validation or improvement claim
is provided. Unit and executable integration tests are offline; CI installs
locked dependencies first and downloads no OMOP dictionary or model weights.

## Optional local OMOP search and the next human gate

After the [B01 local acquisition/verification](b01-metadata.md#local-acquisition-and-real-source-check):

```sh
uv run bindofell search --estate .data/omop-v5.5.0/snapshot.json \
  --requirement "person identifier" --profile field_descriptions --top-k 5
```

That is local search only, with no OMOP benchmark score. Retain the pinned v5.5.0
source hashes and comply with component notices/redistribution obligations before
bundling upstream material. The existing 50-paper ledger is still unavailable;
no reference/digest is fabricated.

The next human-curation gate is **15–20 independently authored, explicitly
provisional OMOP cases** under the [annotation protocol](../benchmark/annotation-protocol.md).
Meaningful OMOP benchmark claims require those actual cases. An independently
validated release additionally requires two independent mapping annotations and
distinct adjudicator sign-off. Their absence does not block synthetic B03
engineering acceptance. Stop for independent review before B04.
