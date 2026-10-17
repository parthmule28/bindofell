"""Local BM25 over B01 channel values; no gold or outcome decisions enter this API."""

import importlib
import math
import unicodedata
from collections.abc import Iterable
from importlib.metadata import version
from typing import Protocol, cast

from pydantic import TypeAdapter

from bindofell.benchmark.io import (
    EligibleUniverse,
    canonical_json,
    content_digest,
    validate_universe,
)
from bindofell.domain.models import BindingCandidate, EstateSnapshot, Evidence, Identifier
from bindofell.evaluation.contracts import MethodSpec
from bindofell.retrieval.documents import (
    PROFILES,
    Profile,
    SearchDocument,
    build_search_documents,
    documents_to_jsonl,
)

TOKENIZER_ID = "bindofell.nfkc-casefold-words/1"
METHOD_ID = "bindofell.bm25/1"


def tokenize(text: str) -> tuple[str, ...]:
    """NFKC, Unicode camel/acronym and letter/digit boundaries, then casefold.

    Separators (including underscore/dot/punctuation) split words. Combining marks
    stay with a word. No stemming, stopwords, synonyms or abbreviation expansion.
    """
    normalized = unicodedata.normalize("NFKC", text)
    tokens: list[str] = []
    word = ""
    for i, char in enumerate(normalized):
        category = unicodedata.category(char)[0]
        if category not in "LNM" or (category == "M" and not word):
            if word:
                tokens.append(word.casefold())
                word = ""
            continue
        previous = word[-1:] or " "
        following = normalized[i + 1 : i + 2]
        boundary = bool(word) and (
            (previous.islower() and char.isupper())
            or (previous.isupper() and char.isupper() and following.islower())
            or (previous.isalnum() and char.isalnum() and previous.isnumeric() != char.isnumeric())
        )
        if boundary:
            tokens.append(word.casefold())
            word = ""
        word += char
    if word:
        tokens.append(word.casefold())
    return tuple(tokens)


class _Scorer(Protocol):
    def index(self, corpus: list[list[str]], *, show_progress: bool) -> None: ...
    def get_scores(self, query: list[str]) -> Iterable[float]: ...


class _Factory(Protocol):
    def __call__(
        self,
        *,
        method: str,
        idf_method: str,
        k1: float,
        b: float,
        delta: float,
        dtype: str,
        int_dtype: str,
        backend: str,
        csc_backend: str,
        auto_compile: bool,
    ) -> _Scorer: ...


class LexicalIndex:
    def __init__(
        self,
        snapshot: EstateSnapshot,
        universe: EligibleUniverse,
        *,
        profile: Profile,
        documents: Iterable[SearchDocument] | None = None,
    ):
        validate_universe(universe, snapshot)
        if profile not in PROFILES:
            raise ValueError(f"unknown profile: {profile}")
        self.snapshot = snapshot
        self.universe = universe
        eligible = set(universe.field_ids)
        expected = tuple(
            sorted(
                (
                    d
                    for d in build_search_documents(snapshot, profile=profile)
                    if d.field_id in eligible
                ),
                key=lambda d: d.field_id,
            )
        )
        supplied = (
            expected if documents is None else tuple(sorted(documents, key=lambda d: d.field_id))
        )
        if supplied != expected:
            raise ValueError(
                "documents must exactly match the B01 snapshot/profile "
                "and complete eligible universe"
            )
        self.documents = supplied
        self.documents_digest = content_digest(documents_to_jsonl(self.documents))
        self.tokens = tuple(
            tokenize("\n".join(c.value for c in d.channels)) for d in self.documents
        )
        self.tokens_digest = content_digest(
            canonical_json(
                [
                    {"field_id": d.field_id, "tokens": t}
                    for d, t in zip(self.documents, self.tokens, strict=True)
                ]
            )
        )
        self.method = MethodSpec(
            method_id=METHOD_ID,
            version="1",
            indexed_field_ids=universe.field_ids,
            universe_digest=universe.digest,
            config={
                "package": "bm25s",
                "package_version": version("bm25s"),
                "method": "lucene",
                "idf_method": "lucene",
                "k1": 1.5,
                "b": 0.75,
                "delta": 0.5,
                "dtype": "float64",
                "int_dtype": "int32",
                "backend": "numpy",
                "csc_backend": "numpy",
                "auto_compile": False,
                "create_empty_token": True,
                "profile": profile,
                "tokenizer_id": TOKENIZER_ID,
                "unicode_version": unicodedata.unidata_version,
                "text_projection": "channel-values/1",
                "stopwords": "none",
                "stemming": "none",
            },
        )
        self._scorer: _Scorer | None = None
        if any(self.tokens):
            # Typed boundary for bm25s's untyped public index/get_scores interface.
            factory = cast(_Factory, importlib.import_module("bm25s").BM25)
            self._scorer = factory(
                method="lucene",
                idf_method="lucene",
                k1=1.5,
                b=0.75,
                delta=0.5,
                dtype="float64",
                int_dtype="int32",
                backend="numpy",
                csc_backend="numpy",
                auto_compile=False,
            )
            self._scorer.index([list(t) for t in self.tokens], show_progress=False)
        sources = {
            e.evidence_id: e
            for asset in (*snapshot.tables, *snapshot.fields)
            for e in asset.evidence
        }
        self._evidence = {
            d.field_id: tuple(
                sources[i]
                for i in sorted({i for c in d.channels for i in c.evidence_ids})
                if i in sources
            )
            for d in self.documents
        }

    def search(
        self,
        text: str,
        *,
        requirement_id: str,
        top_k: int | None = 5,
    ) -> tuple[BindingCandidate, ...]:
        TypeAdapter(Identifier).validate_python(requirement_id)
        if top_k is not None and (type(top_k) is not int or top_k < 1):
            raise ValueError("top_k must be a positive integer or None for the full ranking")
        tokens = tokenize(text)
        if not tokens or not self.documents:
            return ()
        scores = (
            [float(s) for s in self._scorer.get_scores(list(tokens))]
            if self._scorer is not None
            else [0.0] * len(self.documents)
        )
        if len(scores) != len(self.documents) or not all(math.isfinite(s) for s in scores):
            raise ValueError("BM25 returned invalid/non-finite scores")
        ordered = sorted(
            zip(self.documents, scores, strict=True), key=lambda pair: (-pair[1], pair[0].field_id)
        )
        query_digest = content_digest(text)
        result: list[BindingCandidate] = []
        for rank, (document, score) in enumerate(ordered[:top_k], 1):
            parameters = {
                **self.method.config,
                "document_digest": self.documents_digest,
                "query_digest": query_digest,
                "raw_score": score,
            }
            evidence_id = content_digest(
                canonical_json([requirement_id, document.field_id, parameters])
            )
            computation = Evidence(
                evidence_id=f"urn:bindofell:evidence:bm25:{evidence_id}",
                kind="computation",
                computation=METHOD_ID,
                computation_version="1",
                input_ids=(requirement_id, self.snapshot.snapshot_id, document.field_id),
                parameters=parameters,
            )
            result.append(
                BindingCandidate(
                    requirement_id=requirement_id,
                    snapshot_id=self.snapshot.snapshot_id,
                    field_id=document.field_id,
                    rank=rank,
                    raw_score=score,
                    method_id=self.method.method_id,
                    method_config=self.method.config,
                    evidence=(*self._evidence[document.field_id], computation),
                )
            )
        return tuple(result)
