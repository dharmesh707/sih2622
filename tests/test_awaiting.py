"""F-03: pending AUTO_MATCHED events stay reachable until a planner confirms, rejects or reviews them."""
from fastapi.testclient import TestClient

from backend.app import app

CONFIDENT = "Piping crew completed spool XX102 at rack 3, 100%."


def _pending_ids(client, project_id=1):
    return [e["id"] for e in client.get(f"/api/v1/awaiting-confirmation?project_id={project_id}").json()]


def test_abandoned_auto_match_is_listed_confirmed_once_then_gone():
    with TestClient(app) as client:
        body = client.post("/api/v1/reports", json={"text": CONFIDENT}).json()
        assert body["match"]["decision"] == "AUTO_MATCHED"
        # the ingest screen is left without confirming: the event must still be reachable
        pending = client.get("/api/v1/awaiting-confirmation?project_id=1").json()
        item = next(e for e in pending if e["id"] == body["event_id"])
        assert item["activity_code"] == "PIP-L5-002" and item["project_id"] == 1
        assert item["source_text"] == CONFIDENT and item["reason"] and item["top_score"] > 0.82
        assert all(q["id"] != body["event_id"] for q in client.get("/api/v1/review-queue").json())

        activity_id = item["activity_id"]
        assert client.post(f"/api/v1/events/{body['event_id']}/confirm", json={"activity_id": activity_id}).status_code == 200
        assert body["event_id"] not in _pending_ids(client)
        second = client.post(f"/api/v1/events/{body['event_id']}/confirm", json={"activity_id": activity_id})
        assert second.status_code == 409
        audit = [a for a in client.get("/api/v1/audit").json() if a["event_id"] == body["event_id"]]
        assert len(audit) == 1
        assert client.get(f"/api/v1/activities/{activity_id}").json()["percent_complete"] == 100


def test_pending_auto_match_can_be_sent_to_review_or_rejected():
    with TestClient(app) as client:
        a = client.post("/api/v1/reports", json={"text": CONFIDENT}).json()["event_id"]
        assert client.post(f"/api/v1/events/{a}/send-to-review", json={"comment": "check line"}).status_code == 200
        assert a not in _pending_ids(client)
        assert any(q["id"] == a and q["decision"] == "REVIEW_REQUIRED" for q in client.get("/api/v1/review-queue").json())
        assert client.post(f"/api/v1/events/{a}/send-to-review", json={}).status_code == 409  # no longer AUTO

        b = client.post("/api/v1/reports", json={"text": CONFIDENT}).json()["event_id"]
        assert client.post(f"/api/v1/events/{b}/reject", json={}).status_code == 200
        assert b not in _pending_ids(client)


def test_abandoned_time_agent_confirmation_is_reachable_by_planner():
    with TestClient(app) as client:
        reply = client.post("/api/v1/agent/message", json={"text": CONFIDENT}).json()
        assert reply["state"] == "awaiting_confirmation"
        assert reply["event_id"] in _pending_ids(client)  # the supervisor walked away before "yes"


def test_awaiting_list_is_project_scoped():
    with TestClient(app) as client:
        event_id = client.post("/api/v1/reports", json={"text": CONFIDENT}).json()["event_id"]
        assert event_id not in _pending_ids(client, project_id=2)
