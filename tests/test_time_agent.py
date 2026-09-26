"""Phase 6: Time Agent session persistence, real clarification, same-event continuation, confirmation."""
from fastapi.testclient import TestClient

from backend.app import app


def _say(client, text, session_id=None, project_id=1):
    body = {"project_id": project_id, "text": text}
    if session_id:
        body["session_id"] = session_id
    response = client.post("/api/v1/agent/message", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_clarification_resolves_same_event_then_confirms():
    with TestClient(app) as client:
        first = _say(client, "XX102 started at 9.")
        session, event_id = first["session_id"], first["event_id"]
        assert first["state"] == "clarifying" and first["match"]["decision"] != "AUTO_MATCHED"
        assert "location" in first["reply"].lower()  # asks for the missing context, not a canned line

        second = _say(client, "Rack 3.", session)
        assert second["event_id"] == event_id  # same pending event, not a new report
        assert second["event"]["location_terms"] == "R03" and "Rack 3." in second["event"]["source_text"]
        assert second["state"] == "awaiting_confirmation" and "PIP-L5-002" in second["reply"]
        assert client.get(f"/api/v1/activities/{second['match']['activity_id']}").json()["status"] == "not_started"  # nothing written yet

        third = _say(client, "yes", session)
        assert third["state"] == "idle" and third["confirmation"]["new"]["status"] == "in_progress"
        audit = [row for row in client.get("/api/v1/audit").json() if row["event_id"] == event_id]
        assert len(audit) == 1 and audit[0]["actor"].startswith("supervisor via time agent")

        stored = client.get(f"/api/v1/agent/sessions/{session}").json()
        assert [m["role"] for m in stored["messages"]] == ["user", "agent"] * 3
        assert stored["state"] == "idle"


def test_one_report_per_conversation_and_session_isolation():
    with TestClient(app) as client:
        a = _say(client, "XX102 started at 9.")
        b = _say(client, "XX102 started at 9.")
        assert a["session_id"] != b["session_id"] and a["event_id"] != b["event_id"]
        _say(client, "Rack 3.", a["session_id"])
        with_reports = client.get("/api/v1/review-queue").json()
        assert sum(1 for item in with_reports if item["id"] == a["event_id"]) <= 1


def test_no_sends_to_review_and_writes_nothing():
    with TestClient(app) as client:
        first = _say(client, "Piping crew completed spool XX102 at rack 3, 100%.")
        assert first["state"] == "awaiting_confirmation"
        second = _say(client, "no", first["session_id"])
        assert second["state"] == "idle" and "review" in second["reply"]
        queue = client.get("/api/v1/review-queue").json()
        assert any(item["id"] == first["event_id"] and item["decision"] == "REVIEW_REQUIRED" for item in queue)
        assert not [row for row in client.get("/api/v1/audit").json() if row["event_id"] == first["event_id"]]


def test_unresolved_after_max_rounds_is_left_for_planner():
    with TestClient(app) as client:
        first = _say(client, "ZZ-999 unknown activity at offshore platform, 20%.")
        assert first["state"] == "clarifying"
        second = _say(client, "not sure", first["session_id"])
        third = _say(client, "still no idea", first["session_id"])
        assert third["state"] == "idle" and "nothing was written" in third["reply"]
        assert second["event_id"] == first["event_id"]
        assert any(item["id"] == first["event_id"] for item in client.get("/api/v1/review-queue").json())


def test_supervisor_can_pick_a_candidate_by_code():
    with TestClient(app) as client:
        first = _say(client, "Piping crew working at rack 3, spool aligned, 50%.")
        assert first["state"] == "clarifying"
        second = _say(client, "It is PIP-L5-023", first["session_id"])
        assert second["state"] == "awaiting_confirmation" and "you picked it" in second["reply"]
        third = _say(client, "confirm", first["session_id"])
        assert third["confirmation"]["activity"]["activity_code"] == "PIP-L5-023"
        assert third["confirmation"]["approval_status"] in {"approved", "reassigned"}
