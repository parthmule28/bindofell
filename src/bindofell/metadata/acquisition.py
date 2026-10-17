"""Pinned OMOP acquisition and offline verification. Outputs stay local by default."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal, cast
from urllib.request import Request, urlopen

from pydantic import AwareDatetime, Field

from bindofell.domain.models import Contract, Digest, Identifier, SourceDigest, Text
from bindofell.metadata.adapters.omop import ADAPTER_ID, OMOP_REVISION, load_omop
from bindofell.metadata.loader import snapshot_to_json

TABLE_FILE = "OMOP_CDMv5.5_Table_Level.csv"
FIELD_FILE = "OMOP_CDMv5.5_Field_Level.csv"
TAG_API = "https://api.github.com/repos/OHDSI/CommonDataModel/commits/v5.5.0"
SOURCE_URI = f"https://github.com/OHDSI/CommonDataModel/tree/{OMOP_REVISION}"
PINNED_HASHES = {
    TABLE_FILE: "42553b33bd7ec7085b0bc8df029fc6fd83aaa12650686bb259c4d492a10eb95d",
    FIELD_FILE: "7089ca523c13a29ec42ae55d4ef857a67bde0718a777c221858fad029b939994",
    "DESCRIPTION": "88a1f1f5ba02ecc694b327d3a989b3cb97ed1cb6c12092c84094ce49f95f7aed",
}


class AcquisitionManifest(Contract):
    schema_version: Literal["1.0"] = "1.0"
    source_version: Literal["5.5.0"] = "5.5.0"
    source_revision: Text
    source_uri: Text
    adapter_id: Text
    license: Literal["Apache License 2.0"] = "Apache License 2.0"
    retrieved_at: AwareDatetime
    source_digests: tuple[SourceDigest, ...]
    snapshot_id: Identifier
    snapshot_sha256: Digest
    table_count: Annotated[int, Field(ge=0, strict=True)]
    field_count: Annotated[int, Field(ge=0, strict=True)]
    relationship_count: Annotated[int, Field(ge=0, strict=True)]


def _download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "bindofell/0.1 metadata acquisition"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _verify_files(raw: dict[str, bytes]) -> None:
    if set(raw) != set(PINNED_HASHES):
        raise ValueError("source files do not match the pinned file set")
    for name, value in raw.items():
        if _sha(value) != PINNED_HASHES[name]:
            raise ValueError(f"{name}: SHA-256 mismatch against reviewed source lock")
    if b"License: Apache License 2.0" not in raw["DESCRIPTION"]:
        raise ValueError("DESCRIPTION license declaration does not match reviewed source")


def acquire_omop(
    output_dir: str | Path,
    *,
    fetch: Callable[[str], bytes] = _download,
    retrieved_at: datetime | None = None,
) -> AcquisitionManifest:
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"{output}: refusing to overwrite an existing acquisition")
    info = json.loads(fetch(TAG_API))
    if not isinstance(info, dict) or cast(dict[str, object], info).get("sha") != OMOP_REVISION:
        raise ValueError("v5.5.0 tag no longer resolves to the reviewed revision")
    raw: dict[str, bytes] = {}
    for name in PINNED_HASHES:
        relative = name if name == "DESCRIPTION" else f"inst/csv/{name}"
        url = f"https://raw.githubusercontent.com/OHDSI/CommonDataModel/{OMOP_REVISION}/{relative}"
        raw[name] = fetch(url)
    _verify_files(raw)
    timestamp = retrieved_at or datetime.now(UTC)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="bindofell-omop-", dir=output.parent) as staging:
        stage = Path(staging)
        for name, content in raw.items():
            (stage / name).write_bytes(content)
        estate = load_omop(
            stage / TABLE_FILE,
            stage / FIELD_FILE,
            namespace="ohdsi.omop.cdm",
            source_revision=OMOP_REVISION,
            source_uri=SOURCE_URI,
            expected_digests={k: PINNED_HASHES[k] for k in (TABLE_FILE, FIELD_FILE)},
            retrieved_at=timestamp,
            license="Apache License 2.0",
        )
        snapshot = snapshot_to_json(estate).encode("utf-8")
        manifest = AcquisitionManifest(
            source_revision=OMOP_REVISION,
            source_uri=SOURCE_URI,
            adapter_id=ADAPTER_ID,
            retrieved_at=timestamp,
            source_digests=tuple(
                SourceDigest(path=k, sha256=PINNED_HASHES[k]) for k in sorted(PINNED_HASHES)
            ),
            snapshot_id=estate.snapshot_id,
            snapshot_sha256=_sha(snapshot),
            table_count=len(estate.tables),
            field_count=len(estate.fields),
            relationship_count=len(estate.relationships),
        )
    output.mkdir(exist_ok=False)
    artifacts = {
        **raw,
        "snapshot.json": snapshot,
        "manifest.json": (manifest.model_dump_json(indent=2) + "\n").encode(),
    }
    for name, content in artifacts.items():
        with (output / name).open("xb") as stream:
            stream.write(content)
    return manifest


def verify_acquisition(directory: str | Path) -> AcquisitionManifest:
    """Verify source locks, reimported snapshot bytes and observed counts without network."""
    directory = Path(directory)
    manifest = AcquisitionManifest.model_validate_json((directory / "manifest.json").read_bytes())
    if (
        manifest.source_revision != OMOP_REVISION
        or manifest.source_uri != SOURCE_URI
        or manifest.adapter_id != ADAPTER_ID
    ):
        raise ValueError("manifest source revision/adapter does not match reviewed source lock")
    if (
        len(manifest.source_digests) != len(PINNED_HASHES)
        or {d.path: d.sha256 for d in manifest.source_digests} != PINNED_HASHES
    ):
        raise ValueError("manifest digests do not match reviewed source lock")
    raw = {name: (directory / name).read_bytes() for name in PINNED_HASHES}
    _verify_files(raw)
    estate = load_omop(
        directory / TABLE_FILE,
        directory / FIELD_FILE,
        namespace="ohdsi.omop.cdm",
        source_revision=OMOP_REVISION,
        source_uri=SOURCE_URI,
        retrieved_at=manifest.retrieved_at,
        expected_digests={k: PINNED_HASHES[k] for k in (TABLE_FILE, FIELD_FILE)},
        license=manifest.license,
    )
    snapshot = (directory / "snapshot.json").read_bytes()
    if (
        snapshot != snapshot_to_json(estate).encode()
        or _sha(snapshot) != manifest.snapshot_sha256
        or estate.snapshot_id != manifest.snapshot_id
        or (len(estate.tables), len(estate.fields), len(estate.relationships))
        != (manifest.table_count, manifest.field_count, manifest.relationship_count)
    ):
        raise ValueError("snapshot or observed counts differ from verified source import")
    return manifest
