"""B03 manifests: static evidence/configuration separated from runtime observations."""

import hashlib
import math
import os
import platform
import statistics
import subprocess
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from bindofell.benchmark.io import canonical_json, content_digest, strict_object
from bindofell.domain.models import Attributes, Contract, Digest, Identifier, Text
from bindofell.evaluation.contracts import EvaluationResult, StaticProvenance
from bindofell.evaluation.runner import result_to_json
from bindofell.retrieval.documents import PROFILES
from bindofell.retrieval.lexical import TOKENIZER_ID, LexicalIndex, tokenize

Seconds = Annotated[float, Field(ge=0, strict=True)]
Count = Annotated[int, Field(ge=0, strict=True)]


class GitState(Contract):
    status: Literal["available", "unavailable"]
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] | None = None
    dirty: StrictBool | None = None

    @model_validator(mode="after")
    def availability(self) -> Self:
        if (self.status == "available") != (self.revision is not None and self.dirty is not None):
            raise ValueError("Git availability must match revision and dirty-state observations")
        return self


class ResearchReference(Contract):
    status: Literal["unavailable"] = "unavailable"
    reference: None = None
    digest: None = None


class ToolVersion(Contract):
    name: Text
    version: Text


class OmissionCount(Contract):
    channel: Text
    count: Count


class RunStatic(Contract):
    provenance: StaticProvenance
    documents_digest: Digest
    tokens_digest: Digest
    results_digest: Digest
    gold_digest: Digest
    case_versions: tuple[Text, ...]
    gold_versions: tuple[Text, ...]
    protocol_versions: tuple[Text, ...]
    document_count: Count
    serializer_id: Text
    tokenizer_id: Text
    omitted_channels: tuple[OmissionCount, ...]
    ranking_depth: Literal["full-universe"] = "full-universe"
    mrr_label: Literal["MRR"] = "MRR"
    git: GitState
    lock_sha256: Digest | None
    software: tuple[ToolVersion, ...]
    research: ResearchReference = Field(default_factory=ResearchReference)


class CaseLatency(Contract):
    case_id: Identifier
    seconds: Seconds


class RunObservations(Contract):
    started_at: AwareDatetime
    index_build_seconds: Seconds
    queries: tuple[CaseLatency, ...]
    median_seconds: Seconds | None
    p95_seconds: Seconds | None
    percentile_definition: Literal["nearest-rank ceil(0.95*n)"] = "nearest-rank ceil(0.95*n)"
    warm_state: Text = "index built once; sequential queries; first query unwarmed; no cache flush"
    host: Attributes


class RunManifest(Contract):
    schema_version: Literal["1.0"] = "1.0"
    static: RunStatic
    static_digest: Digest
    observations: RunObservations

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.static_digest != content_digest(
            canonical_json(self.static.model_dump(mode="json"))
        ):
            raise ValueError("manifest static digest mismatch")
        return self


def capture_git(root: Path | None) -> GitState:
    if root is None:
        return GitState(status="unavailable")
    try:

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", "-C", str(root), *args],
                check=True,
                timeout=5,
                capture_output=True,
                text=True,
            ).stdout.strip()

        revision = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
        return GitState(status="available", revision=revision, dirty=dirty)
    except (OSError, subprocess.SubprocessError, ValueError):
        return GitState(status="unavailable")


def lock_digest(path: Path | None) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path is not None else None
    except OSError:
        return None


def capture_host() -> Attributes:
    return {
        "os": platform.platform(),
        "machine": platform.machine() or None,
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        **{
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
    }


def build_manifest(
    result: EvaluationResult,
    index: LexicalIndex,
    *,
    started_at: datetime,
    index_seconds: float,
    query_latencies: tuple[CaseLatency, ...],
    git_root: Path | None,
    lock_path: Path | None,
    host: Attributes | None = None,
) -> RunManifest:
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("run timestamp requires an explicit timezone")
    for record in result.results:
        expected: set[str] = (
            set(index.universe.field_ids) if tokenize(record.case.requirement.text) else set()
        )
        if {c.field_id for c in record.ranking.candidates} != expected:
            raise ValueError("unrestricted MRR requires the full eligible ranking for every case")
    if result.provenance.method != index.method:
        raise ValueError("manifest method differs from evaluated index")
    ids = tuple(q.case_id for q in query_latencies)
    if len(set(ids)) != len(ids) or set(ids) != set(result.included_case_ids):
        raise ValueError("latencies must cover exactly the included cases")
    omissions = Counter(channel for d in index.documents for channel in d.omitted_channels)
    profile = str(index.method.config["profile"])
    static = RunStatic(
        provenance=result.provenance,
        documents_digest=index.documents_digest,
        tokens_digest=index.tokens_digest,
        results_digest=content_digest(result_to_json(result)),
        gold_digest=content_digest(
            canonical_json(
                [
                    {"case_id": r.case.case_id, "gold": r.case.gold.model_dump(mode="json")}
                    for r in result.results
                ]
            )
        ),
        case_versions=tuple(sorted({r.case.case_version for r in result.results})),
        gold_versions=tuple(sorted({r.case.gold.gold_version for r in result.results})),
        protocol_versions=tuple(sorted({r.case.protocol_version for r in result.results})),
        document_count=len(index.documents),
        serializer_id="bindofell.search-document/1.0",
        tokenizer_id=TOKENIZER_ID,
        omitted_channels=tuple(
            OmissionCount(channel=c, count=omissions[c]) for c in PROFILES[profile]
        ),
        git=capture_git(git_root),
        lock_sha256=lock_digest(lock_path),
        software=tuple(
            ToolVersion(name=p, version=version(p))
            for p in ("bindofell", "bm25s", "numpy", "scipy", "pydantic")
        )
        + (ToolVersion(name="python", version=platform.python_version()),),
    )
    values = sorted(q.seconds for q in query_latencies)
    observations = RunObservations(
        started_at=started_at.astimezone(UTC),
        index_build_seconds=index_seconds,
        queries=query_latencies,
        median_seconds=statistics.median(values) if values else None,
        p95_seconds=values[math.ceil(0.95 * len(values)) - 1] if values else None,
        host=host if host is not None else capture_host(),
    )
    return RunManifest(
        static=static,
        static_digest=content_digest(canonical_json(static.model_dump(mode="json"))),
        observations=observations,
    )


def static_projection(manifest: RunManifest) -> str:
    return canonical_json(manifest.static.model_dump(mode="json"))


def manifest_to_json(manifest: RunManifest) -> str:
    return canonical_json(manifest.model_dump(mode="json"))


def manifest_from_json(text: str) -> RunManifest:
    return RunManifest.model_validate(strict_object(text))
