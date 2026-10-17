"""Local argparse entry point. Retrieval scores never approve semantic mappings."""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Literal, cast

from bindofell.benchmark.io import (
    EligibleUniverse,
    canonical_json,
    content_digest,
    make_universe,
    read_utf8,
    strict_object,
    validate_universe,
)
from bindofell.domain.models import (
    BindingCandidate,
    Contract,
    Digest,
    EstateSnapshot,
    FieldAddress,
    Identifier,
    SourceDigest,
    Text,
)
from bindofell.evaluation.contracts import MethodSpec
from bindofell.metadata.loader import load_snapshot
from bindofell.retrieval.documents import PROFILES, Profile, SearchDocument
from bindofell.retrieval.lexical import TOKENIZER_ID, LexicalIndex


class SearchHit(Contract):
    candidate: BindingCandidate
    address: FieldAddress
    document: SearchDocument


class SearchOutput(Contract):
    schema_version: Literal["1.0"] = "1.0"
    snapshot_id: Identifier
    source_digests: tuple[SourceDigest, ...]
    requirement_id: Identifier
    requirement_text: str
    method: MethodSpec
    universe: EligibleUniverse
    documents_digest: Digest
    tokens_digest: Digest
    serializer_id: Text = "bindofell.search-document/1.0"
    tokenizer_id: Text = TOKENIZER_ID
    classification_status: Literal["not_evaluated"] = "not_evaluated"
    results: tuple[SearchHit, ...]


def load_universe(path: Path | None, snapshot: EstateSnapshot) -> EligibleUniverse:
    if path is None:
        return make_universe(snapshot)
    universe = EligibleUniverse.model_validate(strict_object(read_utf8(path)))
    validate_universe(universe, snapshot)
    return universe


def _positive(value: str) -> int:
    try:
        number = int(value)
        if number < 1:
            raise ValueError("not positive")
        return number
    except ValueError as exc:
        raise argparse.ArgumentTypeError("top-k must be a positive integer") from exc


def _write_new_file(path: Path, text: str) -> None:
    """Publish a complete same-directory temporary file atomically, without overwrite."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _search(args: argparse.Namespace) -> None:
    snapshot = load_snapshot(args.estate)
    universe = load_universe(args.universe, snapshot)
    index = LexicalIndex(snapshot, universe, profile=cast(Profile, args.profile))
    requirement_id = f"urn:bindofell:requirement:sha256:{content_digest(args.requirement)}"
    candidates = index.search(args.requirement, requirement_id=requirement_id, top_k=args.top_k)
    fields = {f.field_id: f for f in snapshot.fields}
    documents = {d.field_id: d for d in index.documents}
    output = SearchOutput(
        snapshot_id=snapshot.snapshot_id,
        source_digests=snapshot.source_digests,
        requirement_id=requirement_id,
        requirement_text=args.requirement,
        method=index.method,
        universe=universe,
        documents_digest=index.documents_digest,
        tokens_digest=index.tokens_digest,
        results=tuple(
            SearchHit(
                candidate=c, address=fields[c.field_id].address, document=documents[c.field_id]
            )
            for c in candidates
        ),
    )
    serialized = canonical_json(output.model_dump(mode="json"))
    if args.output is None:
        sys.stdout.write(serialized)
    else:
        _write_new_file(args.output, serialized)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bindofell",
        description=(
            "Local metadata retrieval. Raw BM25 scores are not probabilities or approved mappings."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search", help="rank local physical fields with BM25")
    search.add_argument("--estate", type=Path, required=True)
    search.add_argument("--requirement", required=True)
    search.add_argument("--profile", choices=tuple(PROFILES), default="names")
    search.add_argument("--top-k", type=_positive, default=5)
    search.add_argument("--universe", type=Path, help="frozen eligible-universe JSON manifest")
    search.add_argument("--output", type=Path, help="new JSON file; otherwise print canonical JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        _search(args)
        return 0
    except (ValueError, OSError) as exc:
        print(f"bindofell: error: {exc}", file=sys.stderr)
        return 2
