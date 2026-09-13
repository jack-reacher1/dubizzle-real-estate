import asyncio

from fastapi.testclient import TestClient

from worker.app import app


def test_worker_requires_trigger_secret(monkeypatch):
    monkeypatch.delenv("WORKER_TRIGGER_SECRET", raising=False)
    assert TestClient(app).get("/run").status_code == 503


def test_worker_rejects_invalid_trigger_secret(monkeypatch):
    monkeypatch.setenv("WORKER_TRIGGER_SECRET", "secret")
    assert TestClient(app).get("/run", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_worker_accepts_run_without_waiting_for_scraper(monkeypatch):
    monkeypatch.setenv("WORKER_TRIGGER_SECRET", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")

    class FakeConnection:
        async def fetchval(self, query):
            if query.startswith("SELECT pg_try"):
                return True
            return "00000000-0000-0000-0000-000000000001"

        async def execute(self, *args):
            return None

        async def close(self):
            return None

    async def connect(*args, **kwargs):
        return FakeConnection()

    async def slow_scrape(_run_id):
        await asyncio.sleep(0.05)

    monkeypatch.setattr("worker.app._database_connection", connect)
    monkeypatch.setattr("worker.app._run_scrape_async", slow_scrape)

    response = TestClient(app).get("/run", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"