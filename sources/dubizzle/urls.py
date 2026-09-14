from __future__ import annotations

import os
from urllib.parse import urlparse, urljoin

BASE_URL = os.getenv("DUBIZZLE_BASE_URL", "https://www.dubizzle.com.eg")

SEARCH_URLS = {
    "sale": (
        os.getenv(
            "DUBIZZLE_SALE_URL",
            "https://www.dubizzle.com.eg/en/properties/"
            "apartments-duplex-for-sale/5th-settlement/",
        )
    ),
    "rent": (
        os.getenv(
            "DUBIZZLE_RENT_URL",
            "https://www.dubizzle.com.eg/en/properties/"
            "apartments-duplex-for-rent/5th-settlement/",
        )
    ),
}


def normalize_authoritative_url(raw_url: str | None) -> str | None:
    """Keep the current Dubizzle URL normalization behavior in one place."""
    if not raw_url:
        return None

    value = raw_url.strip()
    if not value:
        return None

    if value.startswith("//"):
        value = "https:" + value

    if value.startswith("/"):
        if value.startswith("/en/ad/") or value.startswith("/ad/"):
            return f"{BASE_URL}{value}"
        return None

    try:
        parsed = urlparse(value)
    except Exception:
        return None

    host = (parsed.netloc or "").lower()
    if not host:
        return None

    allowed_hosts = {
        "dubizzle.com.eg",
        "www.dubizzle.com.eg",
        "olx.com.eg",
        "www.olx.com.eg",
    }

    if host not in allowed_hosts:
        return None

    path = parsed.path.lower()
    if "/en/ad/" not in path and "/ad/" not in path:
        return None

    return value


def build_dubizzle_ad_url(hit: dict) -> str | None:
    """Return an authoritative Dubizzle detail URL only if the source payload contains one."""
    candidates = []

    possible_keys = [
        "ad_url", "url", "canonical_url", "canonicalUrl", "listing_url",
        "listingUrl", "seo_url", "seoUrl", "absolute_url", "absoluteUrl",
        "canonical", "permalink", "page_url", "pageUrl", "href", "link",
    ]

    for key in possible_keys:
        value = hit.get(key)
        if isinstance(value, str):
            candidates.append(value)

    def walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_lower = str(key).lower()
                if isinstance(value, str) and any(
                    token in key_lower for token in (
                        "url", "link", "href", "canonical", "seo",
                        "permalink", "path",
                    )
                ):
                    candidates.append(value)
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(hit)

    for candidate in candidates:
        normalized = normalize_authoritative_url(candidate)
        if normalized:
            return normalized

    return None
