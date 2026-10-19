import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests/fixtures/benchmark"


def cli(*args, console=False):
    entry = Path(sys.executable).parent / "bindofell"
    if console:
        assert entry.is_file(), "registered bindofell console executable missing"
    command = [str(entry)] if console else [sys.executable, "-m", "bindofell"]
    return subprocess.run([*command, *map(str, args)], cwd=ROOT, capture_output=True, text=True)


def search_args(profile="names"):
    return [
        "search",
        "--estate",
        FIXTURES / "toy_estate.json",
        "--requirement",
        "Alpha key",
        "--profile",
        profile,
    ]


def test_both_registered_entrypoints_have_one_help_contract():
    module = cli("--help")
    assert module.returncode == 0, module.stderr
    console = cli("--help", console=True)
    assert console.returncode == 0, console.stderr
    assert "search" in module.stdout and module.stdout == console.stdout


@pytest.mark.parametrize("profile", ["names", "field_descriptions", "table_context"])
def test_search_writes_canonical_physical_candidates_and_evidence(tmp_path, profile):
    from bindofell.benchmark.io import canonical_json

    out = tmp_path / "search.json"
    result = cli(*search_args(profile), "--top-k", "3", "--output", out)
    assert result.returncode == 0, result.stderr
    value = json.loads(out.read_text())
    assert out.read_text() == canonical_json(value)
    assert value["requirement_id"] == (
        "urn:bindofell:requirement:sha256:" + hashlib.sha256(b"Alpha key").hexdigest()
    )
    assert len(value["results"]) == 3
    assert value["method"]["config"]["profile"] == profile
    assert value["classification_status"] == "not_evaluated"
    first = value["results"][0]
    assert first["candidate"]["rank"] == 1
    assert first["candidate"]["field_id"].endswith("/table=Alpha/column=key")
    assert first["candidate"]["raw_score"] > 0
    assert first["address"]["table"] == "Alpha" and first["address"]["schema"] is None
    assert any(e["kind"] == "computation" for e in first["candidate"]["evidence"])
    again = cli(*search_args(profile), "--top-k", "3")
    assert again.returncode == 0 and again.stdout == out.read_text()


@pytest.mark.parametrize(
    "extra",
    [
        ["--top-k", "0"],
        ["--top-k", "-3"],
        ["--profile", "unknown"],
        ["--estate", "/missing/snapshot"],
    ],
)
def test_invalid_search_fails_without_success_artifact(tmp_path, extra):
    out = tmp_path / "not-created.json"
    result = cli(*search_args(), *extra, "--output", out)
    assert result.returncode != 0 and result.stderr
    assert not out.exists()


def test_search_never_overwrites_and_empty_query_is_not_a_classification(tmp_path):
    out = tmp_path / "existing.json"
    out.write_text("preserved")
    assert cli(*search_args(), "--output", out).returncode != 0
    assert out.read_text() == "preserved"
    result = cli(*search_args(), "--requirement", " !?__ ")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["results"] == []
    assert json.loads(result.stdout)["classification_status"] == "not_evaluated"


def test_explicit_eligible_universe_is_used_and_invalid_universe_fails(tmp_path):
    from bindofell.benchmark.io import canonical_json, make_universe
    from bindofell.metadata.loader import load_snapshot

    snapshot = load_snapshot(FIXTURES / "toy_estate.json")
    universe = make_universe(
        snapshot, field_ids=(snapshot.fields[0].field_id,), rule_id="urn:toy:eligibility:one"
    )
    path = tmp_path / "universe.json"
    path.write_text(canonical_json(universe.model_dump(mode="json")))
    result = cli(*search_args(), "--universe", path)
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)["results"]) == 1
    value = universe.model_dump(mode="json")
    value["snapshot_id"] = "urn:toy:wrong"
    path.write_text(json.dumps(value))
    assert cli(*search_args(), "--universe", path).returncode != 0
