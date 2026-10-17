import hashlib
import json

import pytest


def transport(monkeypatch, omop_files):
    from bindofell.metadata import acquisition as a

    data = {
        a.TABLE_FILE: omop_files[0].read_bytes(),
        a.FIELD_FILE: omop_files[1].read_bytes(),
        "DESCRIPTION": b"Synthetic test package\nLicense: Apache License 2.0\n",
    }
    monkeypatch.setattr(
        a, "PINNED_HASHES", {k: hashlib.sha256(v).hexdigest() for k, v in data.items()}
    )

    def fetch(url):
        if url == a.TAG_API:
            return json.dumps({"sha": a.OMOP_REVISION}).encode()
        return data[url.rsplit("/", 1)[1]]

    return a, data, fetch


def test_acquisition_writes_verified_manifest_and_snapshot_without_overwrite(
    monkeypatch, omop_files, tmp_path
):
    a, _, fetch = transport(monkeypatch, omop_files)
    output = tmp_path / "local-source"
    manifest = a.acquire_omop(output, fetch=fetch)
    assert (manifest.table_count, manifest.field_count, manifest.relationship_count) == (2, 3, 1)
    assert manifest.source_revision == a.OMOP_REVISION
    assert a.verify_acquisition(output) == manifest
    assert (output / "snapshot.json").is_file()
    with pytest.raises(FileExistsError):
        a.acquire_omop(output, fetch=fetch)


def test_acquisition_rejects_moved_tag_and_corrupt_download(monkeypatch, omop_files, tmp_path):
    a, data, fetch = transport(monkeypatch, omop_files)
    with pytest.raises(ValueError, match="tag.*revision"):
        a.acquire_omop(tmp_path / "moved", fetch=lambda url: b'{"sha":"changed"}')
    data[a.FIELD_FILE] += b"tampered"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        a.acquire_omop(tmp_path / "corrupt", fetch=fetch)
    assert not (tmp_path / "corrupt").exists()


@pytest.mark.parametrize("filename", ["snapshot.json", "DESCRIPTION", "manifest.json"])
def test_offline_verifier_rejects_tampering(monkeypatch, omop_files, tmp_path, filename):
    a, _, fetch = transport(monkeypatch, omop_files)
    output = tmp_path / "local-source"
    a.acquire_omop(output, fetch=fetch)
    if filename == "manifest.json":
        text = json.loads((output / filename).read_text())
        text["field_count"] = 999
        (output / filename).write_text(json.dumps(text))
    else:
        with (output / filename).open("ab") as stream:
            stream.write(b"tampered")
    with pytest.raises(ValueError):
        a.verify_acquisition(output)
