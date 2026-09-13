from fastapi.testclient import TestClient

import cron
from app import app


class FakeResponse:
    status_code = 202
    text = "accepted"

    def json(self):
        return {"status": "accepted", "run_id": "run-1"}


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, headers):
        self.url = url
        self.headers = headers
        return FakeResponse()


def test_get_with_valid_auth_reaches_scraper(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "secret")
    monkeypatch.setenv("WORKER_URL", "https://worker.example.com")
    monkeypatch.setenv("WORKER_TRIGGER_SECRET", "worker-secret")
    monkeypatch.setattr(cron.httpx, "AsyncClient", FakeClient)

    response = TestClient(app).get(
        "/api/cron/scrape",
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 200
    assert response.json()["worker"]["status"] == "accepted"


def test_invalid_auth_is_rejected(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "secret")
    response = TestClient(app).get(
        "/api/cron/scrape",
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_missing_secret_is_safe(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    response = TestClient(app).get("/api/cron/scrape")
    assert response.status_code == 503


def test_worker_rejection_is_forwarded(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "secret")
    monkeypatch.setenv("WORKER_URL", "https://worker.example.com")
    monkeypatch.setenv("WORKER_TRIGGER_SECRET", "worker-secret")

    class ConflictResponse(FakeResponse):
        status_code = 409

    class ConflictClient(FakeClient):
        async def get(self, url, headers):
            return ConflictResponse()

    monkeypatch.setattr(cron.httpx, "AsyncClient", ConflictClient)

    response = TestClient(app).get(
        "/api/cron/scrape",
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 409