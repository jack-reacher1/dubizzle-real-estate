from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_non_numeric_price():
    r = client.get("/api/listings?max_price=abc")
    assert r.status_code == 400
    assert "max_price" in r.json().get("detail", "")


def test_negative_price():
    r = client.get("/api/listings?min_price=-10")
    assert r.status_code == 400
    assert "min_price" in r.json().get("detail", "")


def test_negative_bedrooms():
    r = client.get("/api/listings?bedrooms_min=-1")
    assert r.status_code == 400
    assert "bedrooms_min" in r.json().get("detail", "")


def test_invalid_page():
    r = client.get("/api/listings?page=0")
    assert r.status_code == 400
    assert "page" in r.json().get("detail", "")


def test_invalid_per_page():
    r = client.get("/api/listings?per_page=0")
    assert r.status_code == 400
    assert "per_page" in r.json().get("detail", "")


def test_per_page_too_large():
    r = client.get("/api/listings?per_page=1000")
    assert r.status_code == 400
    assert "per_page" in r.json().get("detail", "")


def test_unsupported_sort():
    r = client.get("/api/listings?sort=weird_sort")
    assert r.status_code == 400
    assert "Invalid sort" in r.json().get("detail", "")


def test_invalid_freshness():
    r = client.get("/api/listings?freshness=-3")
    assert r.status_code == 400
    assert "freshness" in r.json().get("detail", "")


def test_unknown_param_rejected():
    r = client.get("/api/listings?evil_param=1")
    assert r.status_code == 400
    assert "Unknown query parameters" in r.json().get("detail", "")


def test_valid_minimal_request():
    r = client.get("/api/listings")
    assert r.status_code == 200
    j = r.json()
    assert "results" in j
