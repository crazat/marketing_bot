import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from middleware.auth import APIKeyMiddleware


def _client(monkeypatch):
    monkeypatch.setenv("MARKETING_BOT_API_KEY", "secret")

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
    app.add_middleware(APIKeyMiddleware, enabled=True)

    @app.get("/api/secret")
    def secret():
        return {"ok": True}

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/hud/mission/demo/progress/stream")
    def stream_probe():
        return {"ok": True}

    return TestClient(app)


def test_api_get_requires_key(monkeypatch):
    client = _client(monkeypatch)

    assert client.get("/api/secret").status_code == 401
    assert client.get("/api/secret", headers={"X-API-Key": "secret"}).status_code == 200


def test_public_health_stays_public(monkeypatch):
    client = _client(monkeypatch)

    assert client.get("/api/health").status_code == 200


def test_cors_preflight_is_not_api_key_blocked(monkeypatch):
    client = _client(monkeypatch)

    response = client.options(
        "/api/secret",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "x-api-key,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_stream_endpoint_accepts_query_key(monkeypatch):
    client = _client(monkeypatch)

    assert client.get("/api/hud/mission/demo/progress/stream").status_code == 401
    response = client.get("/api/hud/mission/demo/progress/stream?api_key=secret")

    assert response.status_code == 200
