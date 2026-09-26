"""Small hardening items: F-08 future report dates, F-10 agent project isolation, F-11 short-code selection."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import app, code_named

D = lambda n: (date.today() + timedelta(days=n)).isoformat()


# --- F-08 ------------------------------------------------------------------------------------------

def test_future_report_date_is_rejected_and_nothing_is_stored():
    with TestClient(app) as client:
        before = len(client.get("/api/v1/review-queue").json())
        response = client.post("/api/v1/reports", json={"text": "Spool XX102 at rack 3, 30%.", "report_date": D(1)})
        assert response.status_code == 422 and "future" in response.text
        assert len(client.get("/api/v1/review-queue").json()) == before


@pytest.mark.parametrize("offset", [0, -1, -30])
def test_today_and_past_report_dates_still_work(offset):
    with TestClient(app) as client:
        body = client.post("/api/v1/reports", json={"text": "Spool XX102 at rack 3, 30%.", "report_date": D(offset)}).json()
        assert body["event"]["event_timestamp"] == D(offset)


# --- F-10 ------------------------------------------------------------------------------------------

def test_session_never_crosses_projects():
    csv = f"activity_code,description,planned_start,planned_finish,discipline,location\nQ-1,Erect line XX901 spool,{D(-1)},{D(2)},piping,R01\n".encode()
    with TestClient(app) as client:
        client.post("/api/v1/projects/7/schedule/import", files={"file": ("q.csv", csv, "text/csv")})
        first = client.post("/api/v1/agent/message", json={"project_id": 1, "text": "XX106 started at 9."}).json()
        other = client.post("/api/v1/agent/message", json={"project_id": 7, "text": "hello", "session_id": first["session_id"]}).json()
        assert other["session_id"] != first["session_id"]
        original = client.get(f"/api/v1/agent/sessions/{first['session_id']}").json()
        assert original["project_id"] == 1 and original["state"] == first["state"]  # untouched
        assert len(original["messages"]) == 2
        fresh = client.get(f"/api/v1/agent/sessions/{other['session_id']}").json()
        assert fresh["project_id"] == 7 and all("XX106" not in m["text"] for m in fresh["messages"])
        assert client.get(f"/api/v1/agent/sessions/{first['session_id']}?project_id=7").status_code == 404


# --- F-11 ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("code,text,expected", [
    ("A1", "Area 1 is where we are", False),
    ("A1", "a1b is the tag", False),
    ("A1", "It is A1.", True),
    ("A1", "a1", True),
    ("PIP-L5-023", "It is PIP-L5-023", True),
    ("PIP-L5-02", "It is PIP-L5-023", False),
    ("L5-023", "It is PIP-L5-023", False),
])
def test_code_named_is_whole_token(code, text, expected):
    assert code_named(code, text) is expected


def test_short_code_is_not_picked_from_unrelated_text():
    csv = ("activity_code,description,planned_start,planned_finish,discipline,location\n"
           f"A1,Erect piping segment at R01 north,{D(-1)},{D(2)},piping,R01\n"
           f"A2,Erect piping segment at R01 south,{D(-1)},{D(2)},piping,R01\n").encode()
    with TestClient(app) as client:
        client.post("/api/v1/projects/9/schedule/import", files={"file": ("a.csv", csv, "text/csv")})
        first = client.post("/api/v1/agent/message", json={"project_id": 9, "text": "Piping segment at R01 erected, 40%."}).json()
        assert first["state"] == "clarifying"
        second = client.post("/api/v1/agent/message", json={"project_id": 9, "session_id": first["session_id"], "text": "Area 1 crew"}).json()
        assert "you picked it" not in second["reply"]
        third = client.post("/api/v1/agent/message", json={"project_id": 9, "session_id": first["session_id"], "text": "It is A1."}).json()
        assert third["state"] == "awaiting_confirmation" and "A1" in third["reply"] and "you picked it" in third["reply"]
