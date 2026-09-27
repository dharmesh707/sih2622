from fastapi.testclient import TestClient


def test_api_token_is_optional_for_local_use(monkeypatch):
    monkeypatch.delenv("PROGRESSSYNC_API_TOKEN", raising=False)
    from backend.app import app

    with TestClient(app) as client:
        response = client.get("/api/v1/projects")

    assert response.status_code == 200


def test_configured_api_token_protects_api_routes(monkeypatch):
    monkeypatch.setenv("PROGRESSSYNC_API_TOKEN", "demo-secret")
    from backend.app import app

    with TestClient(app) as client:
        missing = client.get("/api/v1/projects")
        invalid = client.get("/api/v1/projects", headers={"Authorization": "Bearer wrong"})
        valid = client.get("/api/v1/projects", headers={"Authorization": "Bearer demo-secret"})
        static = client.get("/")

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert static.status_code in {200, 503}


def test_options_preflight_does_not_require_token(monkeypatch):
    monkeypatch.setenv("PROGRESSSYNC_API_TOKEN", "demo-secret")
    from backend.app import app

    with TestClient(app) as client:
        response = client.options(
            "/api/v1/projects",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"