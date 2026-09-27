import os
import io
from pathlib import Path

os.environ["PROGRESSSYNC_DB"] = str(Path(__file__).parents[1] / "data" / "test.db")

from fastapi.testclient import TestClient

from backend.app import app


def test_report_match_candidates_and_explainability():
    with TestClient(app) as client:
        response = client.post("/api/v1/reports", json={"text": "Piping crew completed spool XX102 at rack 3, 100%.", "source": "text"})
        assert response.status_code == 200
        body = response.json()
        assert body["event"]["discipline"] == "piping"
        assert body["match"]["decision"] in {"AUTO_MATCHED", "REVIEW_REQUIRED"}
        candidates = client.get(f"/api/v1/events/{body['event_id']}/candidates").json()
        assert candidates
        assert {"score_id", "score_lexical", "score_semantic", "score_context", "temporal_factor", "fused_score"}.issubset(candidates[0])
        assert "mapped_terms" in candidates[0]["evidence"]


def test_review_confirm_writes_actual_and_audit():
    with TestClient(app) as client:
        report = client.post("/api/v1/reports", json={"text": "Piping crew working at rack 3, spool aligned, 50%.", "source": "text"}).json()
        event_id = report["event_id"]
        queue = client.get("/api/v1/review-queue").json()
        assert any(item["id"] == event_id for item in queue)
        candidates = client.get(f"/api/v1/events/{event_id}/candidates").json()
        activity_id = candidates[0]["activity_id"]
        confirmed = client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": activity_id, "actor": "planner", "comment": "verified rack evidence"})
        assert confirmed.status_code == 200
        assert confirmed.json()["new"]["percent_complete"] == 50
        audit = client.get("/api/v1/audit").json()
        assert audit and audit[0]["activity_id"] == activity_id
        activity = client.get(f"/api/v1/activities/{activity_id}").json()
        assert activity["percent_complete"] == 50


def test_unmatched_is_preserved_and_agent_uses_same_pipeline():
    with TestClient(app) as client:
        unmatched = client.post("/api/v1/reports", json={"text": "ZZ-999 unknown activity at offshore platform, 20%.", "source": "diary"}).json()
        assert unmatched["event_id"]
        assert unmatched["match"]["decision"] in {"UNMATCHED", "REVIEW_REQUIRED"}
        agent = client.post("/api/v1/agent/message", json={"text": "Pump CT103 installed at Unit 2, 50%.", "session_id": "demo"})
        assert agent.status_code == 200
        assert agent.json()["event"]["report_id"]
        assert agent.json()["reply"]


def test_cpm_and_malformed_import():
    with TestClient(app) as client:
        cpm = client.get("/api/v1/projects/1/critical-path")
        assert cpm.status_code == 200 and cpm.json()
        bad = client.post("/api/v1/projects/1/schedule/import", files={"file": ("bad.txt", b"hello", "text/plain")})
        assert bad.status_code == 415
        missing = client.post("/api/v1/projects/1/schedule/import", files={"file": ("bad.csv", b"activity_code,description\nA,B", "text/csv")})
        assert missing.status_code == 400


def test_xlsx_schedule_import():
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["activity_code", "description", "planned_start", "planned_finish", "discipline", "level"])
    sheet.append(["XLSX-001", "Test piping activity", "2026-09-01", "2026-09-03", "piping", 6])
    stream = io.BytesIO()
    workbook.save(stream)
    with TestClient(app) as client:
        response = client.post("/api/v1/projects/1/schedule/import", files={"file": ("schedule.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert response.status_code == 200
        assert response.json()["inserted"] == 1
