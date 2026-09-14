import importlib
import pytest
from pathlib import Path

scraper = importlib.import_module('scraper')
from scraper import Listing


def test_tracking_runner_script_exists():
    assert Path('scripts/run_scrape_with_tracking.py').exists()


def test_main_fails_when_business_generation_fails(monkeypatch):
    # prepare a fake listing so main thinks it scraped something
    fake = Listing(ad_id='X1', ad_url='u', listing_type='sale')

    monkeypatch.setattr(scraper, 'scrape_search_results', lambda url, lt: [fake])
    # avoid network-heavy broker checks and writes
    monkeypatch.setattr(scraper, 'apply_broker_detection', lambda listings, cache: None)
    monkeypatch.setattr(scraper, 'save_sellers_cache', lambda cache: None)
    monkeypatch.setattr(scraper, 'merge_and_save', lambda listings: None)

    # force generate_business_dataset to raise to simulate failure
    def raise_exc(*a, **k):
        raise Exception('business generation failed')
    monkeypatch.setattr(scraper, 'generate_business_dataset', raise_exc)

    with pytest.raises(SystemExit):
        scraper.main()
