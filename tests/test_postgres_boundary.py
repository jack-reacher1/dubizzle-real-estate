from datetime import datetime, timezone
from pathlib import Path

from database import _db_listing_row, _db_seller_row
import database


def test_postgres_seller_row_matches_csv_representation():
    row = _db_seller_row({
        "seller_id": "seller-1",
        "seller_name": None,
        "profile_url": None,
        "active_ads_count": 0,
        "active_ads_count_source": None,
        "classification": "owner",
        "checked_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "blocklist_permanent": True,
    })

    assert row["active_ads_count"] == "0"
    assert row["checked_at"] == "2026-09-01T00:00:00+00:00"
    assert row["blocklist_permanent"] == "True"
    assert row["seller_name"] == ""
    assert row["active_ads_count_source"] == ""


def test_postgres_null_seller_values_are_empty_csv_values():
    row = _db_seller_row({
        "seller_id": "seller-2",
        "seller_name": None,
        "profile_url": None,
        "active_ads_count": None,
        "active_ads_count_source": None,
        "classification": None,
        "checked_at": None,
        "blocklist_permanent": False,
    })

    assert row["active_ads_count"] == ""
    assert row["checked_at"] == ""
    assert row["blocklist_permanent"] == "False"
    assert row["classification"] == ""


def test_postgres_listing_boolean_and_seen_dates_match_csv_values():
    row = _db_listing_row({
        "ad_id": "ad-1",
        "is_verified_business": True,
        "is_agency": False,
        "has_broker_code_pattern": False,
        "is_active": True,
        "first_seen_date": datetime(2026, 8, 1).date(),
        "last_seen_date": datetime(2026, 9, 1).date(),
    })

    assert row["is_active"] == "True"
    assert row["is_agency"] == "False"
    assert row["first_seen_date"] == "2026-08-01"
    assert row["last_seen_date"] == "2026-09-01"


def test_schema_contains_retention_and_configured_eligibility_rules():
    schema = (Path(__file__).resolve().parents[1] / "scripts" / "002_create_postgres_schema.sql").read_text(encoding="utf-8")
    repository = Path(database.__file__).read_text(encoding="utf-8")
    assert "app_config" in schema
    assert "owner_recheck_days" in schema
    assert "freshness_days" in schema
    assert "DELETE FROM listings" in repository