import csv
from pathlib import Path

from fastapi.testclient import TestClient

import app as app_module
import scraper
from services.listings import ListingsService


def write_listings(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_new_listing_defaults_to_new_and_filters():
    service = ListingsService.from_rows([{"ad_id": "a1", "title": "A1"}])

    result = service.query({"lead_status": "new"})

    assert result["results"][0]["lead_status"] == "new"


def test_csv_patch_persists_status_and_returns_contacted(tmp_path, monkeypatch):
    business_csv = tmp_path / "data" / "business_listings.csv"
    write_listings(business_csv, [{"ad_id": "a1", "title": "A1", "lead_status": "new"}])
    monkeypatch.setattr(app_module.service, "csv_path", business_csv)
    app_module.service._load()
    client = TestClient(app_module.app)

    response = client.patch(
        "/api/listings/a1/lead-status",
        json={"status": "contacted"},
    )

    assert response.status_code == 200
    assert response.json() == {"ad_id": "a1", "lead_status": "contacted"}
    assert app_module.service.get("a1")["lead_status"] == "contacted"
    assert client.get("/api/listings?lead_status=contacted").json()["total"] == 1
    assert client.get("/api/listings?lead_status=new").json()["total"] == 0


def test_csv_scraper_refresh_preserves_contacted_and_updates_fields(tmp_path, monkeypatch):
    listings_csv = tmp_path / "data" / "listings.csv"
    monkeypatch.setattr(scraper, "ADS_CSV", listings_csv)
    monkeypatch.setattr(scraper, "DATA_DIR", listings_csv.parent)
    write_listings(
        listings_csv,
        [{"ad_id": "a1", "title": "Old title", "is_active": "True", "lead_status": "contacted"}],
    )

    listing = scraper.Listing(ad_id="a1", ad_url="https://example.test/a1", listing_type="sale", title="New title")
    scraper.merge_and_save([listing])

    with listings_csv.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["title"] == "New title"
    assert row["lead_status"] == "contacted"


def test_csv_scraper_keeps_unseen_inactive_until_retention(tmp_path, monkeypatch):
    listings_csv = tmp_path / "data" / "listings.csv"
    monkeypatch.setattr(scraper, "ADS_CSV", listings_csv)
    monkeypatch.setattr(scraper, "DATA_DIR", listings_csv.parent)
    write_listings(
        listings_csv,
        [{
            "ad_id": "old",
            "title": "Old",
            "is_active": "True",
            "lead_status": "contacted",
            "last_seen_date": "2026-09-01",
        }],
    )

    scraper.merge_and_save([])

    with listings_csv.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["ad_id"] == "old"
    assert row["is_active"] == "False"


def test_frontend_uses_english_status_values_and_arabic_labels():
    root = Path(__file__).resolve().parents[1]
    template = (root / "templates" / "index_redesign.html").read_text(encoding="utf-8")
    script = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert 'value="new"' in template
    assert 'value="contacted"' in template
    assert "لسه ما اتواصلتش" in template
    assert "تم التواصل" in template
    assert "تواصلت معاه" in script
    assert "status: 'contacted'" in script
