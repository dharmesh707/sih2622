"""Phase 1 regressions: normalization, confirm/reject state machine, 4xx handling, project scoping."""
import pytest
from fastapi.testclient import TestClient

from backend.app import app, extract_event, norm

AMBIGUOUS = "Piping crew working at rack 3, spool aligned, 50%."
CONFIDENT = "Piping crew completed spool XX102 at rack 3, 100%."


# --- normalization -----------------------------------------------------------

@pytest.mark.parametrize("word", ["spool", "boltup", "hydrotest", "erection", "foundation", "concrete", "rotating", "completed"])
def test_norm_keeps_ordinary_words(word):
    assert norm(word) == word


def test_norm_fixes_ocr_zero_only_inside_identifiers():
    assert norm("XX1O2") == norm("XX102") == "xx 102"
    assert norm("RO3") == norm("R03")
    assert norm("CT103") == "ct 103"


@pytest.mark.parametrize("text,discipline", [
    ("Foundation concrete poured at Area A, 40%.", "civil"),
    ("Rotating crew aligned CT103 at Unit 2, 30%.", "rotating_equipment"),
    ("Spool boltup done at rack 3, 60%.", "piping"),
    ("Hydrotest passed on line XX104, 100%.", "piping"),
])
def test_discipline_detection(text, discipline):
    assert extract_event(text, "text", 0)["discipline"] == discipline


def test_completion_inference():
    assert extract_event("Piping crew completed spool XX102 at rack 3.", "text", 0)["progress"] == 100.0
    assert extract_event("Spool XX102 incomplete at rack 3.", "text", 0)["progress"] is None


def test_terminology_and_unknown_signals_through_api():
    with TestClient(app) as client:
        body = client.post("/api/v1/reports", json={"text": CONFIDENT}).json()
        mapped = {t["field_term"] for t in client.get(f"/api/v1/events/{body['event_id']}/candidates").json()[0]["evidence"]["mapped_terms"]}
        assert {"spool", "rack 3"} <= mapped
        pump = client.post("/api/v1/reports", json={"text": "Pump CT103 installed at Unit 2, 50%."}).json()
        top = client.get(f"/api/v1/events/{pump['event_id']}/candidates").json()[0]
        assert "CT-103" in top["description"] and top["score_id"] == 1.0
        unknown = client.post("/api/v1/reports", json={"text": "Unknown work package pressure test done at rack 3, 20%."}).json()
        assert unknown["match"]["decision"] == "UNMATCHED" and unknown["match"]["activity_id"] is None


def test_code_prefix_inside_a_word_is_not_identifier_evidence():
    from backend.app import score_candidate, extract_event
    activity = {"activity_code": "PIP-2107", "description": "Erect piping segment line 2107", "discipline": "piping", "location": "R01", "planned_start": None, "planned_finish": None}
    other = {**activity, "activity_code": "PIP-2104", "description": "Erect piping segment line 2104"}
    event = extract_event("Line 2104 piping segment erected at R01, 100%.", "text", 0)
    assert score_candidate(event, activity, [])[0]["score_id"] == 0.0  # "pip" inside "piping" is not an ID match
    assert score_candidate(event, other, [])[0]["score_id"] == 0.82  # the line number is (line-level evidence, F-04)


# --- confirm / reject state machine -------------------------------------------

def _review_event(client):
    event_id = client.post("/api/v1/reports", json={"text": AMBIGUOUS}).json()["event_id"]
    activity_id = client.get(f"/api/v1/events/{event_id}/candidates").json()[0]["activity_id"]
    return event_id, activity_id


def _audit_rows(client, event_id):
    return [row for row in client.get("/api/v1/audit").json() if row["event_id"] == event_id]


def test_confirm_twice_is_rejected_without_second_write():
    with TestClient(app) as client:
        event_id, activity_id = _review_event(client)
        assert client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": activity_id}).status_code == 200
        assert client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": activity_id}).status_code == 409
        assert len(_audit_rows(client, event_id)) == 1


def test_confirm_then_reject_keeps_approved_state():
    with TestClient(app) as client:
        event_id, activity_id = _review_event(client)
        client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": activity_id})
        assert client.post(f"/api/v1/events/{event_id}/reject", json={}).status_code == 409
        assert client.get(f"/api/v1/events/{event_id}").json()["status"] == "APPROVED"
        assert client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": activity_id}).status_code == 409
        assert len(_audit_rows(client, event_id)) == 1
        assert client.get(f"/api/v1/activities/{activity_id}").json()["percent_complete"] == 50


def test_reject_then_confirm_is_refused_and_schedule_untouched():
    with TestClient(app) as client:
        event_id, activity_id = _review_event(client)
        assert client.post(f"/api/v1/events/{event_id}/reject", json={"comment": "wrong crew"}).status_code == 200
        assert client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": activity_id}).status_code == 409
        assert _audit_rows(client, event_id) == []
        assert client.get(f"/api/v1/activities/{activity_id}").json()["percent_complete"] == 0
        assert all(item["id"] != event_id for item in client.get("/api/v1/review-queue").json())


def test_missing_entities_return_404():
    with TestClient(app) as client:
        assert client.post("/api/v1/events/987654/reject", json={}).status_code == 404
        assert client.post("/api/v1/events/987654/confirm", json={"activity_id": 1}).status_code == 404
        event_id, _ = _review_event(client)
        assert client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": 999999}).status_code == 404
        assert client.post("/api/v1/reports", json={"project_id": 42, "text": CONFIDENT}).status_code == 404


def test_review_required_needs_explicit_activity():
    with TestClient(app) as client:
        event_id, _ = _review_event(client)
        assert client.post(f"/api/v1/events/{event_id}/confirm", json={}).status_code == 400


def test_report_without_progress_cannot_be_applied():
    with TestClient(app) as client:
        body = client.post("/api/v1/reports", json={"text": "Spool XX102 looked at by crew at rack 3."}).json()
        activity_id = client.get(f"/api/v1/events/{body['event_id']}/candidates").json()[0]["activity_id"]
        assert client.post(f"/api/v1/events/{body['event_id']}/confirm", json={"activity_id": activity_id}).status_code == 422


def test_reassign_is_recorded_in_audit():
    with TestClient(app) as client:
        event_id = client.post("/api/v1/reports", json={"text": AMBIGUOUS}).json()["event_id"]
        alternate = client.get(f"/api/v1/events/{event_id}/candidates").json()[1]["activity_id"]
        body = client.post(f"/api/v1/events/{event_id}/confirm", json={"activity_id": alternate}).json()
        assert body["approval_status"] == "reassigned"
        assert _audit_rows(client, event_id)[0]["approval_status"] == "reassigned"


# --- project scoping ------------------------------------------------------------

PROJECT_2_CSV = (
    "activity_code,description,wbs_path,level,discipline,location,planned_start,planned_finish\n"
    "P2-PIP-001,Erect line XX102 spool,WBS/PIPING/R03,6,piping,R03,2026-09-10,2026-09-14\n"
    "P2-PIP-002,Erect line XX103 spool,WBS/PIPING/R03,6,piping,R03,2026-09-12,2026-09-16\n"
).encode()


def test_multi_project_isolation():
    with TestClient(app) as client:
        imported = client.post("/api/v1/projects/2/schedule/import", files={"file": ("p2.csv", PROJECT_2_CSV, "text/csv")}).json()
        assert imported["inserted"] == 2
        p2_ids = {a["id"] for a in client.get("/api/v1/projects/2/activities").json()}
        p1_ids = {a["id"] for a in client.get("/api/v1/projects/1/activities").json()}

        body = client.post("/api/v1/reports", json={"project_id": 2, "text": CONFIDENT}).json()
        candidate_ids = {c["activity_id"] for c in client.get(f"/api/v1/events/{body['event_id']}/candidates").json()}
        assert candidate_ids and candidate_ids <= p2_ids

        wrong = client.post(f"/api/v1/events/{body['event_id']}/confirm", json={"activity_id": min(p1_ids)})
        assert wrong.status_code == 409

        right = client.post(f"/api/v1/events/{body['event_id']}/confirm", json={"activity_id": min(candidate_ids)})
        assert right.status_code == 200
        assert _audit_rows(client, body["event_id"])[0]["project_id"] == 2
        assert all(item["project_id"] == 2 for item in client.get("/api/v1/review-queue?project_id=2").json())
