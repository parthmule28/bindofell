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
    load_cases,
    make_universe,
    read_utf8,
    strict_object,
    validate_universe,
)
from bindofell.benchmark.splits import Partition, assign_splits, manifest_from_json
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
from bindofell.experiments.run import evaluate_experiment, write_experiment
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


def _source_context() -> tuple[Path | None, Path | None]:
    source = Path(__file__).resolve()
    root = source.parents[2]
    if (root / "src/bindofell/cli.py").resolve() != source:
        return None, None  # Installed wheel: do not attribute an unrelated working directory.
    return root, root / "uv.lock"


def _evaluate(args: argparse.Namespace) -> None:
    output: Path = args.output_dir
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"experiment output already exists: {output}")
    snapshot = load_snapshot(args.estate)
    universe = load_universe(args.universe, snapshot)
    cases = load_cases(args.cases, snapshot, universe)
    splits = (
        manifest_from_json(read_utf8(args.split_manifest), cases)
        if args.split_manifest is not None
        else assign_splits(cases, seed=args.seed)
    )
    git_root, lock_path = _source_context()
    result, manifest = evaluate_experiment(
        snapshot,
        cases,
        universe,
        profile=cast(Profile, args.profile),
        split_manifest=splits,
        partition=cast(Partition, args.split) if args.split != "all" else None,
        split_origin="frozen" if args.split_manifest is not None else "generated",
        git_root=git_root,
        lock_path=lock_path,
    )
    write_experiment(output, result, manifest)
    sys.stdout.write(
        canonical_json(
            {
                "direct": result.direct.model_dump(mode="json"),
                "classification": result.classification.status,
                "static_digest": manifest.static_digest,
            }
        )
    )


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
    evaluate = commands.add_parser("evaluate", help="evaluate full BM25 rankings with B02 metrics")
    evaluate.add_argument("--estate", type=Path, required=True)
    evaluate.add_argument("--cases", type=Path, required=True)
    evaluate.add_argument("--split", choices=("train", "validation", "test", "all"), required=True)
    evaluate.add_argument("--profile", choices=tuple(PROFILES), default="names")
    evaluate.add_argument("--universe", type=Path)
    policy = evaluate.add_mutually_exclusive_group(required=True)
    policy.add_argument("--split-manifest", type=Path, help="replay a frozen B02 split manifest")
    policy.add_argument("--seed", type=int, help="generate and record exploratory grouped splits")
    evaluate.add_argument("--output-dir", type=Path, required=True, help="new experiment directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "search":
            _search(args)
        else:
            _evaluate(args)
        return 0
    except (ValueError, OSError) as exc:
        print(f"bindofell: error: {exc}", file=sys.stderr)
        return 2
