"""Optional client_report_id: a retried submission (mobile after a timeout) must not create a second event."""
from fastapi.testclient import TestClient

from backend.app import app

CONFIDENT = "Piping crew completed spool XX102 at rack 3, 100%."


def _event_count(client):
    return len(client.get("/api/v1/awaiting-confirmation?project_id=1").json()) + len(client.get("/api/v1/review-queue?project_id=1").json())


def test_retry_with_same_client_id_replays_original_result():
    with TestClient(app) as client:
        payload = {"project_id": 1, "text": CONFIDENT, "source": "mobile", "client_report_id": "mob-0001-abcd"}
        first = client.post("/api/v1/reports", json=payload)
        second = client.post("/api/v1/reports", json=payload)
        assert first.status_code == second.status_code == 200
        a, b = first.json(), second.json()
        assert (b["report_id"], b["event_id"]) == (a["report_id"], a["event_id"])
        assert b["match"]["decision"] == a["match"]["decision"] == "AUTO_MATCHED"
        assert b["replayed"] is True and "replayed" not in a
        assert _event_count(client) == 1


def test_client_id_reused_for_different_text_is_rejected():
    with TestClient(app) as client:
        client.post("/api/v1/reports", json={"text": CONFIDENT, "client_report_id": "mob-0002-abcd"})
        clash = client.post("/api/v1/reports", json={"text": "Pump CT103 installed at Unit 2, 50%.", "client_report_id": "mob-0002-abcd"})
        assert clash.status_code == 409
        assert _event_count(client) == 1


def test_without_client_id_behaviour_is_unchanged():
    with TestClient(app) as client:
        a = client.post("/api/v1/reports", json={"text": CONFIDENT}).json()
        b = client.post("/api/v1/reports", json={"text": CONFIDENT}).json()
        assert a["event_id"] != b["event_id"] and "replayed" not in b


def test_client_id_is_validated():
    with TestClient(app) as client:
        for bad in ("short", "has spaces in it", "x" * 65, "semi;colon-1234"):
            assert client.post("/api/v1/reports", json={"text": CONFIDENT, "client_report_id": bad}).status_code == 422


def test_replay_does_not_bypass_confirmation():
    with TestClient(app) as client:
        payload = {"text": CONFIDENT, "client_report_id": "mob-0003-abcd"}
        event_id = client.post("/api/v1/reports", json=payload).json()["event_id"]
        before = client.get("/api/v1/activities/2").json()
        client.post("/api/v1/reports", json=payload)
        assert client.get("/api/v1/activities/2").json()["percent_complete"] == before["percent_complete"]
        assert client.get("/api/v1/audit").json() == []
        assert client.get(f"/api/v1/events/{event_id}").json()["decision"]["decision"] == "AUTO_MATCHED"
