"""Phase 9: matching behaviour per category on a small inline schedule (production path via POST /reports)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import app

D = lambda n: (date.today() + timedelta(days=n)).isoformat()
SCHEDULE = (
    "activity_code,description,planned_start,planned_finish,discipline,location\n"
    f"PIP-3001,Erect piping segment line 3001 at R01,{D(-2)},{D(3)},piping,R01\n"
    f"PIP-3002,Erect piping segment line 3002 at R01,{D(-2)},{D(3)},piping,R01\n"
    f"INS-PT201,Calibrate pressure transmitter PT-201,{D(-2)},{D(3)},instrumentation,Unit 2\n"
    f"INS-PT202,Calibrate pressure transmitter PT-202,{D(-2)},{D(3)},instrumentation,Unit 2\n"
    f"ROT-PK401,Install pump PK-401,{D(-2)},{D(3)},rotating_equipment,Unit 3\n"
).encode()


@pytest.fixture
def run():
    with TestClient(app) as client:
        client.post("/api/v1/projects/6/schedule/import", files={"file": ("m.csv", SCHEDULE, "text/csv")})
        codes = {a["id"]: a["activity_code"] for a in client.get("/api/v1/projects/6/activities").json()}

        def _run(text):
            body = client.post("/api/v1/reports", json={"project_id": 6, "text": text}).json()
            top = client.get(f"/api/v1/events/{body['event_id']}/candidates").json()
            return body["match"]["decision"], codes[top[0]["activity_id"]] if top else None
        yield _run


def test_exact(run):
    assert run("Calibrate pressure transmitter PT-201 finished, 100%.") == ("AUTO_MATCHED", "INS-PT201")


def test_synonym_via_terminology(run):
    assert run("Spool line 3002 erected at rack 1, 60%.")[1] == "PIP-3002"


def test_abbreviation(run):
    assert run("PT202 calib done 100%")[1] == "INS-PT202"


def test_typo_and_ocr_zero(run):
    assert run("Calibrate presure transmiter PT-2O1, 50%.")[1] == "INS-PT201"


def test_near_duplicate_is_never_auto(run):
    assert run("Piping segment erected at rack 1, 50%.")[0] != "AUTO_MATCHED"


def test_unknown_is_unmatched(run):
    assert run("Painting of storage tank TK-800 roof, 30%.")[0] == "UNMATCHED"


def test_wrong_discipline_never_auto_matches_a_wrong_activity(run):
    decision, top = run("Piping crew calibrated transmitter PT-201, 100%.")
    assert decision != "AUTO_MATCHED" or top == "INS-PT201"
