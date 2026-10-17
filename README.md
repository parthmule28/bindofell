# Bindofell

Bindofell is a public, research-driven semantic data-binding project. Version 0.1 focuses on reproducible retrieval and evaluation of business concepts to physical table-column mappings.

## B01: metadata foundation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --all-groups
uv run pytest tests/unit/domain tests/unit/metadata tests/unit/retrieval -q
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
use only synthetic fixtures and block network connections. Ranking, benchmark
contracts and `bindofell search/evaluate` are deferred to later work packages.

See [B01 formats and usage](docs/usage/b01-metadata.md), the
[core contracts](docs/design/0001-bindofell-core.md), the
[benchmark specification](docs/design/0002-benchmark-v0.1.md),
[source assessment](docs/datasets/source-assessment.md) and the
[implementation plan](docs/plans/b00-b04-implementation.md).
