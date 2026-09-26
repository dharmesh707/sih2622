"""F-02 / F-13: monotonic progress, consistent completion state, completed candidates down-ranked."""
import threading
from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend.app import app

D = lambda n: (date.today() + timedelta(days=n)).isoformat()


def _activity(client, code, project_id=1):
    return next(a for a in client.get(f"/api/v1/projects/{project_id}/activities").json() if a["activity_code"] == code)


def _report(client, text, project_id=1):
    return client.post("/api/v1/reports", json={"project_id": project_id, "text": text}).json()["event_id"]


def _confirm(client, event_id, activity_id):
    return client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": activity_id})


STATE = ("percent_complete", "status", "actual_start", "actual_finish")


def test_completed_activity_is_not_reopened_by_lower_progress():
    with TestClient(app) as client:
        pip = _activity(client, "PIP-L5-002")
        assert _confirm(client, _report(client, "Piping crew completed spool XX102 at rack 3, 100%."), pip["id"]).status_code == 200
        before = _activity(client, "PIP-L5-002")
        event_id = _report(client, "Completed activity XX102 at rack 3 is now reported at 30%.")
        response = _confirm(client, event_id, pip["id"])
        assert response.status_code == 409 and "already complete" in response.json()["detail"]
        after = _activity(client, "PIP-L5-002")
        assert {k: after[k] for k in STATE} == {k: before[k] for k in STATE}
        assert after["status"] == "complete" and after["percent_complete"] == 100 and after["actual_finish"]
        assert not [a for a in client.get("/api/v1/audit").json() if a["event_id"] == event_id]
        assert client.get(f"/api/v1/events/{event_id}").json()["decision"]["decision"] != "APPROVED"  # still decidable (reject)
        assert client.post(f"/api/v1/events/{event_id}/reject", json={"comment": "stale report"}).status_code == 200


def test_started_report_does_not_reopen_a_completed_activity():
    with TestClient(app) as client:
        civ = _activity(client, "CIV-L5-001")  # seeded as complete
        response = _confirm(client, _report(client, "Foundation concrete works 001 started at Area A."), civ["id"])
        assert response.status_code == 409
        assert _activity(client, "CIV-L5-001")["status"] == "complete"


def test_progress_is_never_decreased_silently():
    with TestClient(app) as client:
        pip = _activity(client, "PIP-L5-009")
        assert _confirm(client, _report(client, "Spool XX103 at rack 3 working, 70%."), pip["id"]).status_code == 200
        response = _confirm(client, _report(client, "Spool XX103 at rack 3 working, 30%."), pip["id"])
        assert response.status_code == 409 and "lower than the current 70%" in response.json()["detail"]
        assert _activity(client, "PIP-L5-009")["percent_complete"] == 70


def test_forward_progress_still_works():
    with TestClient(app) as client:
        pip = _activity(client, "PIP-L5-009")
        assert _confirm(client, _report(client, "Spool XX103 at rack 3 working, 30%."), pip["id"]).status_code == 200
        response = _confirm(client, _report(client, "Spool XX103 at rack 3 working, 70%."), pip["id"])
        assert response.status_code == 200 and response.json()["new"]["percent_complete"] == 70
        assert response.json()["new"]["status"] == "in_progress"


def test_repeat_completion_is_idempotent_and_keeps_first_finish_date():
    with TestClient(app) as client:
        civ = _activity(client, "CIV-L5-001")
        response = _confirm(client, _report(client, "Foundation concrete works 001 at Area A completed, 100%."), civ["id"])
        assert response.status_code == 200
        body = response.json()
        assert body["old"] == body["new"]  # nothing changes, the confirmation is recorded
        assert _activity(client, "CIV-L5-001")["actual_finish"] == civ["actual_finish"]


def test_active_candidate_preferred_over_completed_twin():
    csv = ("activity_code,description,planned_start,planned_finish,discipline,location\n"
           f"TW-A,Erect piping segment at R01 west,{D(-2)},{D(3)},piping,R01\n"
           f"TW-B,Erect piping segment at R01 east,{D(-2)},{D(3)},piping,R01\n").encode()
    with TestClient(app) as client:
        client.post("/api/v1/projects/8/schedule/import", files={"file": ("tw.csv", csv, "text/csv")})
        a = _activity(client, "TW-A", 8)
        assert _confirm(client, _report(client, "Piping segment at R01 west completed, 100%.", 8), a["id"]).status_code == 200
        event_id = _report(client, "Piping segment erection at R01 in progress, 40%.", 8)
        ranked = client.get(f"/api/v1/events/{event_id}/candidates").json()
        codes = {x["activity_id"]: x for x in ranked}
        assert ranked[0]["activity_id"] != a["id"]
        assert codes[a["id"]]["evidence"]["completed_activity"] and codes[a["id"]]["evidence"]["status_factor"] == 0.85


def test_concurrent_confirms_still_approve_once():
    with TestClient(app) as client:
        pip = _activity(client, "PIP-L5-016")
        event_id = _report(client, "Spool XX104 at rack 3 working, 40%.")
        statuses = []

        def hit():
            with TestClient(app, raise_server_exceptions=False) as other:
                statuses.append(_confirm(other, event_id, pip["id"]).status_code)

        threads = [threading.Thread(target=hit) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert sorted(statuses) == [200, 409, 409, 409]
        assert len([a for a in client.get("/api/v1/audit").json() if a["event_id"] == event_id]) == 1
