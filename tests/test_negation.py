"""F-01: negated / future-tense wording must never be inferred as completion or start."""
import pytest
from fastapi.testclient import TestClient

from backend.app import app, extract_event, started_signal

NEGATIVE = [
    "Spool XX102 at rack 3 not completed yet.",
    "Spool XX103 at rack 3 will be completed tomorrow.",
    "Spool XX104 at rack 3 not started due to rain.",
    "Spool XX105 has not started.",
    "Spool XX106 is not finished.",
    "Spool XX107 yet to complete.",
    "Spool XX108 completion is pending.",
    "Spool XX109 will start tomorrow.",
    # hardening prompt section 11 wording
    "Piping crew: spool XX103 at rack 3 not completed yet.",
    "Spool XX104 at rack 3 will be completed tomorrow.",
    "Spool XX105 at rack 3 not started due to rain.",
    "Spool XX106 has not started.",
    "Spool XX107 is not finished.",
    "Spool XX108 yet to complete.",
    "Spool XX109 completion is pending.",
    "Spool XX110 will start tomorrow.",
    # other phrasings from the required list
    "Spool XX102 isn't completed.",
    "Spool XX102 hasn't started.",
    "Spool XX102 is yet to be completed.",
    "Spool XX102 pending start.",
    "Spool XX102 scheduled to start next week.",
    "Spool XX102 expected to be completed Friday.",
    "Spool XX102 to be completed tomorrow.",
    "Spool XX102 will be completed tomorrow, 100%.",
]

POSITIVE = [
    ("Spool XX110 completed at rack 3.", 100.0, False),
    ("Spool XX111 finished at rack 3.", 100.0, False),
    ("Spool XX112 started at rack 3.", None, True),
    ("Spool XX113 installed, 100%.", 100.0, False),
    ("Spool XX120 completed at rack 3.", 100.0, False),
    ("Spool XX121 finished at rack 3.", 100.0, False),
    ("Spool XX122 started at rack 3.", None, True),
    ("Spool XX123 installed, 40%.", 40.0, False),
    ("Spool XX124 installed, 100%.", 100.0, False),
    ("Spool XX102 was not started last week but completed today.", 100.0, False),  # explicit positive overrides
    ("Spool XX102 not completed yet, 60%.", 60.0, False),  # explicit current progress is kept
]


@pytest.mark.parametrize("text", NEGATIVE)
def test_negated_or_future_wording_infers_nothing(text):
    event = extract_event(text, "text", 0)
    assert event["progress"] is None, text
    assert not started_signal(text), text
    assert event["inference_note"] and event["source_text"] == text


@pytest.mark.parametrize("text,progress,started", POSITIVE)
def test_positive_controls_still_work(text, progress, started):
    event = extract_event(text, "text", 0)
    assert event["progress"] == progress, text
    assert started_signal(text) == started, text
    assert event["inference_note"] is None


@pytest.mark.parametrize("text", NEGATIVE[:8])
def test_negated_reports_are_never_auto_and_never_written(text):
    with TestClient(app) as client:
        body = client.post("/api/v1/reports", json={"text": text}).json()
        assert body["match"]["decision"] != "AUTO_MATCHED"
        assert body["event"]["source_text"] == text  # evidence preserved
        top = client.get(f"/api/v1/events/{body['event_id']}/candidates").json()[0]["activity_id"]
        before = client.get(f"/api/v1/activities/{top}").json()
        response = client.post(f"/api/v1/events/{body['event_id']}/confirm", json={"activity_id": top})
        assert response.status_code == 422 and "no progress or start" in response.json()["detail"]
        after = client.get(f"/api/v1/activities/{top}").json()
        for field in ("percent_complete", "status", "actual_start", "actual_finish"):
            assert after[field] == before[field]
        assert not [a for a in client.get("/api/v1/audit").json() if a["event_id"] == body["event_id"]]
        assert any(q["id"] == body["event_id"] for q in client.get("/api/v1/review-queue").json())


def test_confident_negated_match_is_downgraded_with_reason():
    with TestClient(app) as client:
        body = client.post("/api/v1/reports", json={"text": "Piping crew: spool XX102 at rack 3 not completed yet."}).json()
        assert body["match"]["decision"] == "REVIEW_REQUIRED"
        assert "no progress or start" in body["match"]["reason"] and "negated or future" in body["match"]["reason"]


def test_positive_confirm_paths_still_write():
    with TestClient(app) as client:
        done = client.post("/api/v1/reports", json={"text": "Piping crew completed spool XX102 at rack 3, 100%."}).json()
        assert done["match"]["decision"] == "AUTO_MATCHED"
        new = client.post(f"/api/v1/events/{done['event_id']}/confirm", json={}).json()["new"]
        assert new["status"] == "complete" and new["actual_finish"]
        started = client.post("/api/v1/reports", json={"text": "Spool XX103 started at rack 3."}).json()
        top = client.get(f"/api/v1/events/{started['event_id']}/candidates").json()[0]["activity_id"]
        new = client.post(f"/api/v1/events/{started['event_id']}/confirm", json={"activity_id": top}).json()["new"]
        assert new["status"] == "in_progress" and new["actual_start"] and new["actual_finish"] is None


def test_time_agent_does_not_offer_to_record_a_negated_report():
    with TestClient(app) as client:
        reply = client.post("/api/v1/agent/message", json={"text": "Spool XX102 at rack 3 not completed yet."}).json()
        assert reply["state"] != "awaiting_confirmation"
        assert reply["confirmation"] is None
