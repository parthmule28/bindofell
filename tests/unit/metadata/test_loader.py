import json

import pytest


def test_snapshot_roundtrip_is_canonical_across_input_order(estate_payload, tmp_path):
    from bindofell.domain.models import EstateSnapshot
    from bindofell.metadata.loader import (
        load_snapshot,
        snapshot_from_json,
        snapshot_to_json,
        write_snapshot,
    )

    estate = EstateSnapshot.model_validate(estate_payload)
    original = snapshot_to_json(estate)
    assert (
        snapshot_to_json(snapshot_from_json(json.dumps(estate_payload, sort_keys=False)))
        == original
    )
    path = tmp_path / "snapshot.json"
    write_snapshot(estate, path)
    assert snapshot_to_json(load_snapshot(path)) == original
    assert load_snapshot(path) == estate
    assert json.loads(original)["tables"][0]["address"]["schema"] is None


@pytest.mark.parametrize(
    "text,match",
    [
        ("{", "invalid snapshot"),
        ("[]", "invalid snapshot"),
        ('{"schema_version":"9.0"}', "unsupported schema_version"),
        ('{"schema_version":"1.0","schema_version":"9.0"}', "duplicate JSON key"),
        ('{"v":NaN}', "non-finite JSON"),
    ],
)
def test_loader_rejects_invalid_or_unsupported_json(text, match):
    from bindofell.metadata.loader import snapshot_from_json

    with pytest.raises(ValueError, match=match):
        snapshot_from_json(text, source="fixture.json")


def test_loader_error_contains_file_and_field_location(estate_payload, tmp_path):
    from bindofell.metadata.loader import load_snapshot

    estate_payload["fields"][0]["address"]["column"] = ""
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(estate_payload))
    with pytest.raises(ValueError, match=r"bad.json.*invalid snapshot") as error:
        load_snapshot(path)
    assert "fields.0.address.column" in str(error.value)
