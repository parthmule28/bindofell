import json
import socket
from pathlib import Path
from shutil import copyfile

import pytest


@pytest.fixture
def estate_payload():
    path = Path(__file__).parent / "fixtures" / "estate-v1.json"
    return json.loads(path.read_text())


@pytest.fixture
def omop_files(tmp_path):
    fixtures = Path(__file__).parent / "fixtures" / "omop"
    files = tuple(tmp_path / name for name in ("table.csv", "field.csv"))
    for path in files:
        copyfile(fixtures / path.name, path)
    return files


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("unit tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def omop_snapshot(omop_files):
    from bindofell.metadata.adapters.omop import load_omop

    return load_omop(
        *omop_files,
        namespace="synthetic.omop",
        source_revision="synthetic-fixture",
        source_uri="synthetic://omop-shaped",
    )
