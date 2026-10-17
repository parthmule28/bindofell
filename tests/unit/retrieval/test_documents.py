import json

import pytest


def test_profiles_keep_identical_ids_and_separate_source_metadata(omop_snapshot):
    from bindofell.metadata.loader import snapshot_to_json
    from bindofell.retrieval.documents import build_search_documents

    before = snapshot_to_json(omop_snapshot)
    runs = [
        build_search_documents(omop_snapshot, profile=p)
        for p in ("names", "field_descriptions", "table_context")
    ]
    assert len({tuple(d.field_id for d in docs) for docs in runs}) == 1
    ref_docs = [next(d for d in docs if "/column=code_ref" in d.field_id) for docs in runs]
    assert "Synthetic reference" not in ref_docs[0].text
    assert "Synthetic reference" in ref_docs[1].text
    assert "Synthetic entity table" not in ref_docs[1].text
    assert "Synthetic entity table" in ref_docs[2].text
    assert "foreign_key" not in ref_docs[2].text
    assert snapshot_to_json(omop_snapshot) == before


def test_missing_channels_are_omitted_and_evidence_is_traceable(omop_snapshot):
    from bindofell.retrieval.documents import build_search_documents

    docs = build_search_documents(omop_snapshot, profile="field_descriptions")
    key = next(d for d in docs if "/table=entity/column=id" in d.field_id)
    assert "field_guidance" in key.omitted_channels
    assert "field_description" in key.omitted_channels
    assert "None" not in key.text and "NA" not in key.text
    ref = next(d for d in docs if "/column=code_ref" in d.field_id)
    channel = next(c for c in ref.channels if c.name == "field_guidance")
    evidence_ids = {e.evidence_id for f in omop_snapshot.fields for e in f.evidence}
    assert channel.evidence_ids and set(channel.evidence_ids) <= evidence_ids


def test_document_serialization_is_byte_stable_and_order_independent(omop_snapshot):
    from bindofell.retrieval.documents import build_search_documents, documents_to_jsonl

    docs = build_search_documents(omop_snapshot, profile="table_context")
    encoded = documents_to_jsonl(docs)
    assert encoded == documents_to_jsonl(tuple(reversed(docs)))
    assert encoded == documents_to_jsonl(
        build_search_documents(omop_snapshot, profile="table_context")
    )
    rows = [json.loads(row) for row in encoded.splitlines()]
    assert [r["field_id"] for r in rows] == sorted(r["field_id"] for r in rows)
    assert all(r["serializer_id"] == "bindofell.search-document/1.0" for r in rows)


def test_unknown_profile_is_explicit_failure(omop_snapshot):
    from bindofell.retrieval.documents import build_search_documents

    with pytest.raises(ValueError, match="unknown profile"):
        build_search_documents(omop_snapshot, profile="guessed")
