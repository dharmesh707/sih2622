"""F-05: forecast CPM / at-risk flags refresh when the data date moves."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import backend.app as module
from backend.app import app, connect


class _Tomorrow(date):
    offset = 10

    @classmethod
    def today(cls):
        real = date.today()
        return cls(real.year, real.month, real.day) + timedelta(days=cls.offset)


def _latest_snapshot(project_id=1):
    with connect() as db:
        return dict(db.execute("SELECT id, data_date FROM schedule_snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone())


def test_snapshot_records_data_date_and_get_does_not_recompute_needlessly():
    with TestClient(app) as client:
        first = _latest_snapshot()
        assert first["data_date"] == date.today().isoformat()
        client.get("/api/v1/projects/1/activities")
        assert _latest_snapshot()["id"] == first["id"]  # same day: nothing to refresh


def test_data_date_change_refreshes_forecast_on_get(monkeypatch):
    with TestClient(app) as client:
        before = {a["activity_code"]: a for a in client.get("/api/v1/projects/1/activities").json()}
        first = _latest_snapshot()
        monkeypatch.setattr(module, "date", _Tomorrow)  # ten days later, nothing reported
        after = {a["activity_code"]: a for a in client.get("/api/v1/projects/1/activities").json()}
        latest = _latest_snapshot()
        assert latest["id"] != first["id"] and latest["data_date"] == _Tomorrow.today().isoformat()
        assert sum(a["at_risk"] for a in after.values()) > sum(a["at_risk"] for a in before.values())
        assert any("late start" in (a["at_risk_reason"] or "") for a in after.values())
        assert after["HSE-L5-035"]["early_finish"] > before["HSE-L5-035"]["early_finish"]  # forecast moved


def test_critical_path_get_also_refreshes(monkeypatch):
    with TestClient(app) as client:
        first = _latest_snapshot()
        monkeypatch.setattr(module, "date", _Tomorrow)
        assert client.get("/api/v1/projects/1/critical-path").status_code == 200
        assert _latest_snapshot()["id"] != first["id"]


@pytest.mark.parametrize("path", ["/api/v1/projects/1/activities"])
def test_stale_legacy_snapshot_without_data_date_is_refreshed(path):
    with TestClient(app) as client:
        with connect() as db:
            db.execute("UPDATE schedule_snapshots SET data_date=NULL")
            db.commit()
        first = _latest_snapshot()
        client.get(path)
        assert _latest_snapshot()["id"] != first["id"]
