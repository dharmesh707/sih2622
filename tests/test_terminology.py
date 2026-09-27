"""Phase 7: YAML terminology map is the runtime source of truth."""
import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import TERM_PATH, app, connect, load_terms

MAPPINGS = yaml.safe_load(TERM_PATH.read_text(encoding="utf-8"))["mappings"]


def test_api_exposes_exactly_the_yaml_mappings():
    with TestClient(app) as client:
        served = {(t["field_term"], t["canonical_term"], t["discipline"]) for t in client.get("/api/v1/terminology-map").json()}
    assert served == {(m["field_term"], m["canonical_term"], m["discipline"]) for m in MAPPINGS}


@pytest.mark.parametrize("mapping", MAPPINGS, ids=lambda m: m["field_term"])
def test_every_yaml_mapping_is_applied_by_the_matcher(mapping):
    with TestClient(app) as client:
        body = client.post("/api/v1/reports", json={"text": f"Crew {mapping['field_term']} work in progress, 30%."}).json()
        candidate = client.get(f"/api/v1/events/{body['event_id']}/candidates").json()[0]
        applied = {(t["field_term"], t["canonical_term"]) for t in candidate["evidence"]["mapped_terms"]}
    assert (mapping["field_term"], mapping["canonical_term"]) in applied


def test_spool_and_rack3_examples():
    with TestClient(app) as client:
        body = client.post("/api/v1/reports", json={"text": "Spool aligned on rack-3, 40%."}).json()
        applied = {(t["field_term"], t["canonical_term"]) for t in client.get(f"/api/v1/events/{body['event_id']}/candidates").json()[0]["evidence"]["mapped_terms"]}
    assert {("spool", "piping segment"), ("rack 3", "R03")} <= applied


def test_yaml_edits_take_effect_and_bad_files_are_rejected(tmp_path):
    custom = tmp_path / "terms.yaml"
    custom.write_text("version: v2\nsource: test\nmappings:\n  - {field_term: gasket swap, canonical_term: bolting, discipline: piping}\n", encoding="utf-8")
    with connect() as db:
        load_terms(db, custom)
        assert [tuple(r) for r in db.execute("SELECT field_term, canonical_term, version FROM terminology_map")] == [("gasket swap", "bolting", "v2")]
    duplicate = tmp_path / "dup.yaml"
    duplicate.write_text("mappings:\n  - {field_term: rack 3, canonical_term: R03, discipline: piping}\n  - {field_term: rack-3, canonical_term: R03, discipline: piping}\n", encoding="utf-8")
    invalid = tmp_path / "bad.yaml"
    invalid.write_text("mappings:\n  - {field_term: x, canonical_term: y, discipline: plumbing}\n", encoding="utf-8")
    with connect() as db:
        for path in (duplicate, invalid):
            with pytest.raises(ValueError):
                load_terms(db, path)
