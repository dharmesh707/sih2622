"""F-04: single-letter tags and line numbers become identifier evidence; bare numbers need line context."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import app, extract_event

D = lambda n: (date.today() + timedelta(days=n)).isoformat()


@pytest.mark.parametrize("text,expected", [
    ("Install pump P-301, 50%.", ["P-301"]),
    ("Erect vessel V-201, 60%.", ["V-201"]),
    ("Line 2104 piping segment erected at R01, 100%.", ["2104"]),
    ("Ln 2111 spool installed at Rack 3.", ["2111"]),
    ("L-2104 hydrotest started.", ["2104"]),
    ("Line No. 2104 bolted, 40%.", ["2104"]),
    ("P303 installed.", ["P303"]),
    ("Pump P 305 aligned, 100%.", ["P 305"]),
    ("PT-101 tested.", ["PT-101"]),
    ("T-101 set, 30%.", ["T-101"]),
])
def test_identifier_forms_are_extracted(text, expected):
    assert extract_event(text, "text", 0)["identifiers"] == expected


@pytest.mark.parametrize("text", ["Area A 100% complete.", "Crew of 12 at Unit 2, 50%.", "Level 2104 checked.", "Pull 2104 cables."])
def test_random_numbers_are_not_identifiers(text):
    assert extract_event(text, "text", 0)["identifiers"] == []


# Activity codes deliberately do NOT contain the tag digits, as with typical P6 codes.
SCHEDULE = (
    "activity_code,description,planned_start,planned_finish,discipline,location\n"
    f"ROT-A,Install pump P-301,{D(-1)},{D(2)},rotating_equipment,Unit 3\n"
    f"ROT-B,Install pump P-302,{D(-1)},{D(2)},rotating_equipment,Unit 3\n"
    f"STA-A,Erect vessel V-201,{D(-1)},{D(2)},static_equipment,Unit 2\n"
    f"STA-B,Erect vessel V-202,{D(-1)},{D(2)},static_equipment,Unit 2\n"
    f"PIP-A,Erect piping segment line 2104 at R01,{D(-1)},{D(2)},piping,R01\n"
    f"PIP-B,Erect piping segment line 2105 at R01,{D(-1)},{D(2)},piping,R01\n"
    f"PTS-A,Pressure test line 2104,{D(-1)},{D(2)},piping,R01\n"
    f"INS-A,Calibrate pressure transmitter PT-101,{D(-1)},{D(2)},instrumentation,Unit 2\n"
).encode()
LOOKALIKE = (
    "activity_code,description,planned_start,planned_finish,discipline,location\n"
    f"X-ROT,Install pump P-301,{D(-1)},{D(2)},rotating_equipment,Unit 3\n"
).encode()


@pytest.fixture
def client():
    with TestClient(app) as c:
        c.post("/api/v1/projects/11/schedule/import", files={"file": ("s.csv", SCHEDULE, "text/csv")})
        c.post("/api/v1/projects/12/schedule/import", files={"file": ("l.csv", LOOKALIKE, "text/csv")})
        yield c


def _run(client, text):
    codes = {a["id"]: a["activity_code"] for a in client.get("/api/v1/projects/11/activities").json()}
    body = client.post("/api/v1/reports", json={"project_id": 11, "text": text}).json()
    ranked = client.get(f"/api/v1/events/{body['event_id']}/candidates").json()
    return body["match"]["decision"], [(codes.get(c["activity_id"], f"OTHER-{c['activity_id']}"), c["score_id"]) for c in ranked]


@pytest.mark.parametrize("text,truth", [
    ("Install pump P-301, 50%.", "ROT-A"),
    ("Erect vessel V-201, 60%.", "STA-A"),
    ("Install pump P303 or P-302 today, 20%.", "ROT-B"),
    ("PT-101 tested, 100%.", "INS-A"),
])
def test_tag_evidence_reaches_the_right_candidate(client, text, truth):
    decision, ranked = _run(client, text)
    assert ranked[0] == (truth, 1.0)
    assert all(score == 0.0 for code, score in ranked if code != truth and code.split("-")[0] == truth.split("-")[0])


def test_line_number_is_line_level_evidence_shared_by_its_activities(client):
    decision, ranked = _run(client, "Line 2104 piping segment erected at R01, 100%.")
    evidence = {code for code, score in ranked if score > 0}
    assert evidence == {"PIP-A", "PTS-A"}  # both activities of line 2104 get evidence, line 2105 does not
    assert dict(ranked)["PIP-A"] == dict(ranked)["PTS-A"] == 0.82  # line-level, not a unique tag
    assert ranked[0][0] == "PIP-A"  # the wording still separates erect from pressure test
    assert dict(ranked)["PIP-B"] == 0.0


def test_line_number_without_code_digits_now_gives_evidence(client):
    decision, ranked = _run(client, "Ln 2105 spool erected at R01, 40%.")
    assert ranked[0] == ("PIP-B", 0.82)


def test_near_miss_number_is_not_evidence(client):
    decision, ranked = _run(client, "Pressure test on line 210, 100%.")
    assert all(score == 0.0 for _, score in ranked)
    assert decision != "AUTO_MATCHED"


def test_no_cross_project_leakage(client):
    decision, ranked = _run(client, "Install pump P-301, 50%.")
    assert not [code for code, _ in ranked if code.startswith("OTHER")]
