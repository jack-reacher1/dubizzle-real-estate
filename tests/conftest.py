import importlib
import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_test_data(monkeypatch, tmp_path):
    """Keep all CSV reads and writes inside a temporary per-test data directory."""
    monkeypatch.setenv("STORAGE_BACKEND", "csv")
    repo_root = Path(__file__).resolve().parents[1]
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    for name in ("window_state.json", "templates", "static"):
        src = repo_root / name
        if src.exists():
            dst = tmp_path / name
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

    monkeypatch.chdir(tmp_path)

    try:
        app_module = importlib.import_module("app")
        if hasattr(app_module, "service"):
            app_module.service.csv_path = data_dir / "business_listings.csv"
            app_module.service.rows = []
            app_module.service._load()
    except Exception:
        pass

    try:
        listings_module = importlib.import_module("services.listings")
        listings_module.DATA_DIR = data_dir
        listings_module.BUSINESS_CSV = data_dir / "business_listings.csv"
    except Exception:
        pass

    try:
        scraper_module = importlib.import_module("scraper")
        scraper_module.DATA_DIR = data_dir
        scraper_module.ADS_CSV = data_dir / "listings.csv"
        scraper_module.SELLERS_CSV = data_dir / "sellers_cache.csv"
    except Exception:
        pass

    return data_dir
