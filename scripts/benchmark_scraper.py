"""Offline scraper timing benchmark.

This benchmark never contacts Dubizzle and never invokes scraper.main(). It exercises
scrape_search_results with deterministic window.state responses, then reports the
configured request, retry, delay, and processing components separately.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scraper


@dataclass
class MockResponse:
    text: str
    status_code: int = 200
    headers: dict[str, str] | None = None

    def raise_for_status(self):
        return None


def make_hit(identifier: int) -> dict:
    now = int(time.time())
    return {
        "id": str(identifier),
        "state": "active",
        "title": "Benchmark apartment",
        "createdAt": now,
        "updatedAt": now,
        "description": "",
        "contactInfo": {"name": "Benchmark seller"},
        "userExternalID": f"benchmark-seller-{identifier}",
        "formattedExtraFields": [],
        "geography": {},
    }


def make_response(identifier: int, page_count: int) -> MockResponse:
    payload = {
        "algolia": {
            "content": {
                "hits": [make_hit(identifier)],
                "nbPages": page_count,
            }
        }
    }
    return MockResponse(f"window.state = {json.dumps(payload)}")


def measure_category(page_count: int) -> dict:
    calls = 0

    def get_page(_url: str):
        nonlocal calls
        calls += 1
        return make_response(calls, page_count)

    old_get = scraper.polite_get
    old_max_pages = scraper.MAX_PAGES
    scraper.polite_get = get_page
    scraper.MAX_PAGES = page_count
    try:
        started = time.perf_counter()
        listings = scraper.scrape_search_results("https://mock.invalid/search", "sale")
        elapsed = time.perf_counter() - started
    finally:
        scraper.polite_get = old_get
        scraper.MAX_PAGES = old_max_pages

    return {"seconds": elapsed, "requests": calls, "listings": len(listings)}


def main() -> None:
    logging.disable(logging.CRITICAL)
    original_sleep = scraper.time.sleep
    original_uniform = scraper.random.uniform
    try:
        scraper.time.sleep = lambda _seconds: None
        scraper.random.uniform = lambda low, high: (low + high) / 2

        one_page = measure_category(1)
        one_category = measure_category(scraper.MAX_PAGES)
        normal_category = measure_category(min(5, scraper.MAX_PAGES))
        normal_complete = {
            "seconds": normal_category["seconds"] * 2,
            "requests": normal_category["requests"] * 2,
            "listings": normal_category["listings"] * 2,
        }

        attempts = scraper.MAX_RETRIES
        expected_delay = (scraper.MIN_DELAY + scraper.MAX_DELAY) / 2
        print(json.dumps({
            "one_page_processing": one_page,
            "one_category_processing": one_category,
            "normal_complete_processing_5_pages_per_category": normal_complete,
            "configured": {
                "categories": len(scraper.SEARCH_URLS),
                "max_pages": scraper.MAX_PAGES,
                "request_timeout_seconds": scraper.REQUEST_TIMEOUT,
                "max_retries": attempts,
                "delay_min_seconds": scraper.MIN_DELAY,
                "delay_max_seconds": scraper.MAX_DELAY,
                "delay_expected_seconds": expected_delay,
                "backoff_max_seconds": scraper.BACKOFF_MAX_SECONDS,
            },
            "derived": {
                "one_successful_request_delay_seconds": expected_delay,
                "one_request_max_delay_seconds": scraper.MAX_DELAY,
                "max_attempts_per_request": attempts,
                "configured_pages_total": len(scraper.SEARCH_URLS) * scraper.MAX_PAGES,
                "configured_attempts_total": len(scraper.SEARCH_URLS) * scraper.MAX_PAGES * attempts,
            },
        }, indent=2))
    finally:
        scraper.time.sleep = original_sleep
        scraper.random.uniform = original_uniform


if __name__ == "__main__":
    main()
