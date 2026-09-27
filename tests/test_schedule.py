"""Phase 4: dependency import, cycle rejection, relationship types, actual-driven CPM, at-risk rule."""
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app, connect, cpm_state

SAMPLE = (Path(__file__).parents[1] / "data" / "sample_schedule.csv").read_bytes()


def _import(client, project_id, name, payload):
    return client.post(f"/api/v1/projects/{project_id}/schedule/import", files={"file": (name, payload, "text/csv")})


def _day(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


def test_sample_import_persists_dependencies_and_fields():
    with TestClient(app) as client:
        body = _import(client, 3, "sample.csv", SAMPLE).json()
        assert body["inserted"] == 5 and body["dependencies_inserted"] == 4 and body["errors"] == []
        deps = {(d["predecessor_code"], d["successor_code"], d["dependency_type"], d["lag"]) for d in client.get("/api/v1/projects/3/dependencies").json()}
        assert ("CIV-L6-012", "PIP-L6-047", "SS", 1.0) in deps
        pip = next(a for a in client.get("/api/v1/projects/3/activities").json() if a["activity_code"] == "PIP-L6-047")
        assert pip["contractor"] == "Northstar" and pip["resource"] == "Pipe crew"


def test_dependency_only_file_and_row_errors():
    with TestClient(app) as client:
        _import(client, 3, "sample.csv", SAMPLE)
        deps = b"predecessor,successor,relationship,lag\nROT-L6-103,INS-L6-021,FS,0\nNOPE-1,INS-L6-021,FS,0\nCIV-L6-012,PIP-L6-047,XX,0\n"
        body = _import(client, 3, "deps.csv", deps).json()
        assert body["dependencies_inserted"] == 1
        assert {e["row"] for e in body["errors"]} == {3, 4}


def test_cycle_is_rejected_and_nothing_saved():
    with TestClient(app) as client:
        _import(client, 3, "sample.csv", SAMPLE)
        before = client.get("/api/v1/projects/3/dependencies").json()
        response = _import(client, 3, "cycle.csv", b"predecessor,successor\nINS-L6-021,CIV-L6-012\n")
        assert response.status_code == 409 and "cycle" in response.json()["detail"]
        assert client.get("/api/v1/projects/3/dependencies").json() == before


def test_relationship_types_in_planned_cpm():
    csv = (
        "activity_code,description,planned_start,planned_finish,discipline,predecessor,relationship,lag\n"
        f"A,Pour foundation A,{_day(0)},{_day(3)},civil,,,\n"      # 4 days
        f"B,Erect spool B,{_day(0)},{_day(1)},piping,A,SS,2\n"     # starts 2 days after A starts
        f"C,Erect spool C,{_day(0)},{_day(1)},piping,A,FF,1\n"     # finishes 1 day after A finishes
        f"D,Erect spool D,{_day(0)},{_day(1)},piping,C,FS,0\n"
    ).encode()
    with TestClient(app) as client:
        _import(client, 4, "rel.csv", csv)
        with connect() as db:
            state = {v["activity_code"]: v for v in cpm_state(db, 4).values()}
        assert state["B"]["early_start"] == 2
        assert state["C"]["early_finish"] == 5 and state["C"]["early_start"] == 3
        assert state["D"]["early_start"] == 5
        assert state["A"]["critical"] and state["C"]["critical"] and state["D"]["critical"]
        assert not state["B"]["critical"]


def test_actuals_move_the_forecast_and_are_reported():
    csv = (
        "activity_code,description,planned_start,planned_finish,discipline,predecessor\n"
        f"A1,Erect line XX201 spool,{_day(-4)},{_day(-2)},piping,\n"
        f"A2,Erect line XX202 spool,{_day(0)},{_day(1)},piping,A1\n"
    ).encode()
    with TestClient(app) as client:
        _import(client, 5, "late.csv", csv)
        acts = {a["activity_code"]: a for a in client.get("/api/v1/projects/5/activities").json()}
        # A1 should have started 4 days ago: late start -> at risk; A2 is pushed past its planned finish.
        assert acts["A1"]["at_risk"] and "late start" in acts["A1"]["at_risk_reason"]
        assert acts["A2"]["at_risk"] and "forecast finish" in acts["A2"]["at_risk_reason"]

        event_id = client.post("/api/v1/reports", json={"project_id": 5, "text": "Spool XX201 completed at site, 100%."}).json()["event_id"]
        result = client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": acts["A1"]["id"]}).json()
        impact = result["impact"]
        # A1 finishes today (1 day) instead of 3 days from today, so the forecast finish pulls in.
        assert impact["project_finish_change_days"] < 0
        assert impact["float_changes"] == [] or all(f["activity_code"] == "A2" for f in impact["float_changes"])
        after = {a["activity_code"]: a for a in client.get("/api/v1/projects/5/activities").json()}
        assert not after["A1"]["at_risk"] and after["A1"]["status"] == "complete"
        assert not after["A1"]["critical"]


def test_recompute_with_cycle_returns_409():
    with TestClient(app) as client:
        with connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM activities WHERE project_id=1 ORDER BY id LIMIT 2")]
            db.execute("INSERT INTO activity_dependencies(project_id,predecessor_id,successor_id) VALUES (1,?,?)", (ids[1], ids[0]))
            db.commit()
        response = client.post("/api/v1/projects/1/recompute")
        assert response.status_code == 409 and "cycle" in response.json()["detail"]


def test_seed_schedule_is_logically_consistent():
    with connect() as db:
        planned = cpm_state(db, 1)
        acts = {r["id"]: r for r in db.execute("SELECT * FROM activities WHERE project_id=1")}
    origin = min(date.fromisoformat(a["planned_start"]) for a in acts.values())
    for activity_id, values in planned.items():
        assert values["early_start_date"] == acts[activity_id]["planned_start"]
    assert sum(v["critical"] for v in planned.values()) < len(planned)  # parallel work has float
    assert origin == date.today() - timedelta(days=3)
