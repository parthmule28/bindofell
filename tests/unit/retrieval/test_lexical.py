from pathlib import Path

import pytest

from bindofell.benchmark.io import make_universe
from bindofell.domain.models import EstateSnapshot, field_id
from bindofell.metadata.loader import load_snapshot, snapshot_to_json

FIXTURE = Path(__file__).parents[2] / "fixtures/benchmark/toy_estate.json"


def estate():
    return load_snapshot(FIXTURE)


def index(snapshot=None, profile="names"):
    from bindofell.retrieval.lexical import LexicalIndex

    snapshot = snapshot or estate()
    return LexicalIndex(snapshot, make_universe(snapshot), profile=profile)


@pytest.mark.parametrize(
    "text,want",
    [
        (
            "person_id Alpha.key bloodPressure",
            ("person", "id", "alpha", "key", "blood", "pressure"),
        ),
        ("HTTPServer BP2 mmHg", ("http", "server", "bp", "2", "mm", "hg")),
        ("StraßeDate ＣＡＦÉ café", ("strasse", "date", "café", "café")),
        ("αβΓdelta 123.45", ("αβ", "γdelta", "123", "45")),
        ("!?_ .\t", ()),
        ("", ()),
    ],
)
def test_versioned_tokenization(text, want):
    from bindofell.retrieval.lexical import tokenize

    assert tokenize(text) == want


def test_bm25_ranks_relevant_physical_fields_above_distractors():
    result = index().search("Alpha key", requirement_id="urn:toy:q", top_k=None)
    assert result[0].field_id == field_id("toy", "Alpha", "key")
    assert result[0].raw_score > result[-1].raw_score
    assert len(result) == 8
    assert {c.field_id for c in result if "/column=key" in c.field_id} == {
        field_id("toy", "Alpha", "key"),
        field_id("toy", "Beta", "key"),
    }
    assert tuple(c.rank for c in result) == tuple(range(1, 9))
    assert all(
        c.snapshot_id == estate().snapshot_id and c.requirement_id == "urn:toy:q" for c in result
    )
    assert all(c.method_id == "bindofell.bm25/1" for c in result)
    assert all(
        any(e.kind == "computation" and c.field_id in e.input_ids for e in c.evidence)
        for c in result
    )


def test_zero_scores_and_ties_are_deterministic_and_source_is_immutable():
    snapshot = estate()
    before = snapshot_to_json(snapshot)
    one = index(snapshot)
    result = one.search("zzzzUnseen", requirement_id="urn:toy:q", top_k=100)
    assert tuple(c.field_id for c in result) == make_universe(snapshot).field_ids
    assert all(c.raw_score == 0.0 for c in result)
    changed = snapshot.model_copy(update={"fields": tuple(reversed(snapshot.fields))})
    assert index(changed).search("Alpha key", requirement_id="urn:toy:q", top_k=None) == (
        one.search("Alpha key", requirement_id="urn:toy:q", top_k=None)
    )
    assert snapshot_to_json(snapshot) == before


@pytest.mark.parametrize("text", ["", " \t\n", "...__!?"])
def test_no_usable_tokens_returns_explicit_empty_ranking(text):
    assert index().search(text, requirement_id="urn:toy:q", top_k=5) == ()


def test_empty_estate_and_tokenless_documents_do_not_drop_fields():
    snapshot = estate()
    empty = snapshot.model_copy(update={"tables": (), "fields": (), "relationships": ()})
    assert index(empty).search("hello", requirement_id="urn:toy:q") == ()
    value = snapshot.model_dump(mode="json")
    value["fields"] = value["fields"][:1]
    field = value["fields"][0]
    table = next(t for t in value["tables"] if t["table_id"] == field["table_id"])
    from bindofell.domain.models import FieldAddress, TableAddress

    table["address"]["table"] = table["name"] = "."
    table["table_id"] = TableAddress.model_validate(table["address"]).table_id
    field["address"].update(table=".", column="_")
    field.update(
        name="_",
        table_id=table["table_id"],
        field_id=FieldAddress.model_validate(field["address"]).field_id,
    )
    value["tables"] = [table]
    result = index(EstateSnapshot.model_validate(value)).search("hello", requirement_id="urn:toy:q")
    assert len(result) == 1 and result[0].raw_score == 0.0


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5, "5"])
def test_invalid_top_k_fails(top_k):
    with pytest.raises(ValueError, match="top_k"):
        index().search("key", requirement_id="urn:toy:q", top_k=top_k)


def test_unknown_profile_fails():
    with pytest.raises(ValueError, match="profile"):
        index(profile="unknown")
