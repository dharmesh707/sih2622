"""Phase 5: planned-vs-actual variance, productivity, delay causes, institutional memory."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend.app import activity_type, app, connect

TODAY = date.today()


def _project_with(client, project_id, rows):
    header = "activity_code,description,planned_start,planned_finish,discipline,location\n"
    body = "".join(f"{code},{desc},{ps.isoformat()},{pf.isoformat()},{disc},{loc}\n" for code, desc, ps, pf, disc, loc in rows)
    assert client.post(f"/api/v1/projects/{project_id}/schedule/import", files={"file": ("s.csv", (header + body).encode(), "text/csv")}).status_code == 200
    return {a["activity_code"]: a["id"] for a in client.get(f"/api/v1/projects/{project_id}/activities").json()}


def _confirm(client, project_id, text, activity_id, **extra):
    event_id = client.post("/api/v1/reports", json={"project_id": project_id, "text": text}).json()["event_id"]
    response = client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": activity_id, **extra})
    assert response.status_code == 200, response.text
    return event_id


def test_activity_type_strips_identifiers():
    assert activity_type("Erect line XX102 spool 002") == "erect line spool"
    assert activity_type("Install pump CT-103 004") == "install pump"


def test_actual_duration_is_null_until_finished_then_real():
    with TestClient(app) as client:
        ids = _project_with(client, 7, [("P7-A", "Erect line XX301 spool", TODAY - timedelta(days=5), TODAY - timedelta(days=2), "piping", "R07")])
        _confirm(client, 7, "Spool XX301 started, 40%.", ids["P7-A"])
        mem = client.get("/api/v1/memory/similar?project_id=7").json()
        assert mem[0]["actual_start"] == TODAY.isoformat() and mem[0]["actual_duration"] is None
        assert mem[0]["start_variance"] == 5  # started 5 days after plan
        var = client.get("/api/v1/analytics/variance?project_id=7").json()
        assert var["activities"][0]["actual_duration"] is None and var["summary"]["completed"] == 0


def test_completion_records_variance_delay_cause_and_memory():
    with TestClient(app) as client:
        ids = _project_with(client, 8, [
            ("P8-A", "Erect line XX401 spool", TODAY - timedelta(days=3), TODAY - timedelta(days=1), "piping", "R08"),
            ("P8-B", "Install cable tray", TODAY, TODAY + timedelta(days=2), "electrical", "R08"),
        ])
        event_id = _confirm(client, 8, "Spool XX401 completed, 100%.", ids["P8-A"], delay_cause="material", comment="flanges arrived late")
        var = client.get("/api/v1/analytics/variance?project_id=8").json()["activities"][0]
        assert var["actual_duration"] == 1 and var["planned_duration"] == 3 and var["duration_variance"] == -2
        assert var["start_variance"] == 3 and var["finish_variance"] == 1

        delays = client.get("/api/v1/analytics/delay-causes?project_id=8").json()
        assert delays["counts"] == [{"cause": "material", "count": 1}] and delays["weekly"]

        mem = client.get("/api/v1/memory/similar?project_id=8&description=erect line spool").json()[0]
        assert mem["activity_code"] == "P8-A" and mem["delay_cause"] == "material" and mem["notes"] == "flanges arrived late"
        assert mem["actual_duration"] == 1 and mem["planned_duration"] == 3

        # A delay cause can also be added later to an approved event.
        assert client.post(f"/api/v1/events/{event_id}/delay-cause", json={"cause": "weather"}).status_code == 200
        assert client.post(f"/api/v1/events/{event_id}/delay-cause", json={"cause": "aliens"}).status_code == 422

        prod = {(p["discipline"], p["activity_type"]): p for p in client.get("/api/v1/analytics/discipline-productivity?project_id=8").json()}
        assert prod[("piping", "erect line spool")]["avg_actual_duration"] == 1
        assert prod[("electrical", "install cable tray")]["avg_actual_duration"] is None


def test_memory_filters_are_project_aware():
    with TestClient(app) as client:
        ids = _project_with(client, 9, [("P9-A", "Erect line XX501 spool", TODAY, TODAY, "piping", "R09")])
        _confirm(client, 9, "Spool XX501 completed, 100%.", ids["P9-A"])
        assert all(r["project_id"] == 9 for r in client.get("/api/v1/memory/similar?project_id=9").json())
        assert client.get("/api/v1/memory/similar?project_id=9&discipline=civil").json() == []
        assert client.get("/api/v1/memory/similar?project_id=9&location=r09").json()[0]["activity_code"] == "P9-A"
        all_projects = {r["project_id"] for r in client.get("/api/v1/memory/similar").json()}
        assert {1, 9} <= all_projects  # seed history in project 1 + this project


def test_invalid_delay_cause_blocks_confirm_without_writes():
    with TestClient(app) as client:
        ids = _project_with(client, 10, [("P10-A", "Erect line XX601 spool", TODAY, TODAY, "piping", "R10")])
        event_id = client.post("/api/v1/reports", json={"project_id": 10, "text": "Spool XX601 completed, 100%."}).json()["event_id"]
        assert client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": ids["P10-A"], "delay_cause": "bogus"}).status_code == 422
        with connect() as db:
            assert db.execute("SELECT percent_complete FROM activities WHERE id=?", (ids["P10-A"],)).fetchone()[0] == 0
