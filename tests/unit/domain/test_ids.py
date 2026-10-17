import pytest


def test_identity_encodes_optional_segments_without_collision():
    from bindofell.domain.models import field_id, table_id

    addresses = [
        field_id("estate", "T", "C"),
        field_id("estate", "T", "C", schema="x"),
        field_id("estate", "T", "C", catalog="x"),
        field_id("estate", "T", "C", catalog="x", schema="y"),
        field_id("estate", "T/C", "C"),
        field_id("estate", "T", "C/C"),
        field_id("estate", "t", "C"),
        field_id("other", "T", "C"),
        field_id("estate", "T%2FC", "C"),
    ]
    assert len(set(addresses)) == len(addresses)
    assert field_id("estate", "T", "C") == addresses[0]
    assert "%2F" in addresses[4]
    assert table_id("estate", "T", schema="x") != table_id("estate", "T", catalog="x")


@pytest.mark.parametrize(
    "args,kwargs",
    [
        (("", "T", "C"), {}),
        (("ns", "", "C"), {}),
        (("ns", "T", ""), {}),
        (("ns", "T", "C"), {"schema": ""}),
        (("ns", "T", "C"), {"catalog": " "}),
        (("ns", " T", "C"), {}),
    ],
)
def test_identity_rejects_incomplete_or_ambiguous_address(args, kwargs):
    from bindofell.domain.models import field_id

    with pytest.raises(ValueError):
        field_id(*args, **kwargs)
