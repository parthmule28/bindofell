# Bindofell

Bindofell is a public, research-driven semantic data-binding project. Version 0.1 focuses on reproducible retrieval and evaluation of business concepts to physical table-column mappings.

## B01: metadata foundation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked --all-groups
uv run pytest tests/unit tests/integration -q -W error
uv run ruff check
uv run pyright
```

Load the synthetic snapshot and construct attributable text documents:

```python
from bindofell.metadata.loader import load_snapshot
from bindofell.retrieval.documents import build_search_documents

estate = load_snapshot("tests/fixtures/estate-v1.json")
documents = build_search_documents(estate, profile="names")
print(documents[0].field_id, documents[0].text)
```

Acquire and verify the pinned OMOP dictionary locally:

```sh
uv run python scripts/fetch_omop_metadata.py
uv run python scripts/fetch_omop_metadata.py --verify-only
```

The default `.data/omop-v5.5.0/` output is ignored by Git. Acquisition refuses
overwrites and checks the release commit and reviewed file hashes. Unit tests
use only synthetic fixtures and block network connections. B03 now provides
local BM25 search/evaluation through the CLI below.

See [B01 formats and usage](docs/usage/b01-metadata.md), the
[core contracts](docs/design/0001-bindofell-core.md), the
[benchmark specification](docs/design/0002-benchmark-v0.1.md),
[source assessment](docs/datasets/source-assessment.md) and the
[implementation plan](docs/plans/b00-b04-implementation.md).

## B02: benchmark and evaluation foundation

Versioned A/B/C annotations, frozen eligible universes, deterministic grouped
splits and exact metrics can now evaluate supplied synthetic rankings offline.
Outcome classification requires explicit, separate decisions for every included
case; rankings alone do not classify no-match or clarification. Results preserve
case/gold versions, annotation grade, evidence, raw scores and static provenance.

See the runnable [B02 usage example](docs/usage/b02-benchmark.md),
[annotation protocol](docs/benchmark/annotation-protocol.md) and
[synthetic fixtures](tests/fixtures/benchmark/README.md). No real OMOP pilot or
independently validated gold is included. B02 was independently reviewed and
merged before B03 implementation.


## B03: local BM25 search and reproducible evaluation

```sh
uv run bindofell search --estate tests/fixtures/benchmark/toy_estate.json --requirement "Alpha key" --profile names --top-k 5
mkdir -p .data/b03-smoke
uv run bindofell evaluate --estate tests/fixtures/benchmark/toy_estate.json --cases tests/fixtures/benchmark/toy_cases.jsonl --split all --seed 17 --profile names --output-dir .data/b03-smoke/run-a
```

`python -m bindofell` exposes the same commands. Search emits qualified field
IDs, raw scores and source/computation evidence. Evaluation uses all eligible
fields for unrestricted MRR and delegates metrics to B02. No B/C classifier or
approved mapping is inferred. `--seed` and `--split all` are exploratory;
use a frozen `--split-manifest` for reviewed partition replay.

Read [CLI formats, tokenization, manifests and twice-run smoke checks](docs/usage/cli.md).
The two-table/eight-field/three-case fixture is an engineering demonstration;
no real OMOP accuracy or expert gold is claimed. B03 stops for independent review
before B04.
