"""
Dubizzle Egypt - 5th Settlement Real Estate Scraper
====================================================

Scrapes apartment/property listings (sale + rent) in the 5th Settlement
(New Cairo), applies broker-detection rules, seller verification, persistent
seller cache, and maintains a cumulative historical listings.csv dataset.

Data architecture:

    Dubizzle
        |
        v
    scraper.py
        |
        +--> data/listings.csv
        |       Historical cumulative dataset
        |       Upsert by ad_id
        |
        +--> data/sellers_cache.csv
        |       Persistent seller memory
        |       Owner/broker classification
        |       Permanent blacklist
        |       active_ads_count provenance
        |
        +--> data/business_listings.csv
                Current eligible business-facing snapshot

Important:
- listings.csv is cumulative and never intentionally loses historical rows.
- sellers_cache.csv is persistent and preserves old sellers / blacklist entries.
- business_listings.csv is intentionally rebuilt as the CURRENT eligible snapshot.
- No fake Dubizzle ad URLs are constructed.
- Real ad URLs are resolved from actual rendered Dubizzle search-page anchors
  when a strong listing-to-anchor match exists.
"""

import csv
import json
import random
import re
import time
import logging

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin, unquote
from difflib import SequenceMatcher
from html import unescape

import requests


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://www.dubizzle.com.eg"

SEARCH_URLS = {
    "sale": (
        "https://www.dubizzle.com.eg/en/properties/"
        "apartments-duplex-for-sale/5th-settlement/"
    ),
    "rent": (
        "https://www.dubizzle.com.eg/en/properties/"
        "apartments-duplex-for-rent/5th-settlement/"
    ),
}

# Scrape enough pages to capture recent opportunities.
MAX_PAGES = 25

DATA_DIR = Path("data")

ADS_CSV = DATA_DIR / "listings.csv"
SELLERS_CSV = DATA_DIR / "sellers_cache.csv"
BUSINESS_CSV = DATA_DIR / "business_listings.csv"
SCRAPE_STATUS_JSON = DATA_DIR / "scrape_status.json"

OWNER_RECHECK_DAYS = 30
BROKER_ACTIVE_ADS_THRESHOLD = 4

MIN_DELAY = 3
MAX_DELAY = 8

# Seller profile pages can be large.
REQUEST_TIMEOUT = 90
MAX_RETRIES = 2

# Current business-facing freshness requirement.
FRESHNESS_DAYS = 14

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

BROKER_CODE_PATTERN = re.compile(
    r"\bكود\s*[:\-]?\s*[A-Za-z0-9\u0660-\u0669]{2,10}\b"
)

PHONE_PATTERN = re.compile(
    r"01[0125][\s\-]?\d{4}[\s\-]?\d{4}"
)


# ---------------------------------------------------------------------------
# Historical listings schema
# ---------------------------------------------------------------------------

ALL_FIELDS = [
    "ad_id",
    "ad_url",
    "listing_type",
    "property_type",
    "title",
    "price",
    "area_sqm",
    "bedrooms",
    "bathrooms",
    "completion_status",
    "payment_method",
    "ownership",
    "furnished",
    "location_text",
    "compound",
    "location_link",
    "amenities",
    "description_full",
    "phone_in_description",
    "posted_at",
    "updated_at",
    "scraped_at",
    "days_since_updated",
    "is_verified_business",
    "is_agency",
    "agency_name",
    "has_broker_code_pattern",
    "seller_repeat_count",
    "seller_id",
    "seller_name",
    "first_seen_date",
    "last_seen_date",
    "is_active",
]


# ---------------------------------------------------------------------------
# Business dataset schema
# ---------------------------------------------------------------------------

BUSINESS_FIELDS = [
    "ad_id",
    "ad_url",
    "listing_type",
    "title",
    "price",
    "area_sqm",
    "bedrooms",
    "bathrooms",
    "property_type",
    "completion_status",
    "payment_method",
    "furnished",
    "location_text",
    "compound",
    "description_full",
    "posted_at",
    "updated_at",
    "days_since_updated",
    "seller_name",
    "active_ads_count",
    "likely_owner",
]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)

log = logging.getLogger("dubizzle_scraper")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Listing:
    ad_id: str
    ad_url: Optional[str]
    listing_type: str
    property_type: Optional[str] = None
    title: Optional[str] = None
    price: Optional[str] = None
    area_sqm: Optional[str] = None
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None
    completion_status: Optional[str] = None
    payment_method: Optional[str] = None
    ownership: Optional[str] = None
    furnished: Optional[str] = None
    location_text: Optional[str] = None
    compound: Optional[str] = None
    location_link: Optional[str] = None
    amenities: Optional[str] = None
    description_full: Optional[str] = None
    phone_in_description: Optional[str] = None
    posted_at: Optional[str] = None
    updated_at: Optional[str] = None
    scraped_at: Optional[str] = None
    days_since_updated: Optional[int] = None
    is_verified_business: bool = False
    is_agency: bool = False
    agency_name: Optional[str] = None
    has_broker_code_pattern: bool = False
    seller_repeat_count: int = 0
    seller_id: Optional[str] = None
    seller_name: Optional[str] = None
    first_seen_date: Optional[str] = None
    last_seen_date: Optional[str] = None
    is_active: bool = True


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def polite_get(url: str) -> Optional[requests.Response]:
    """
    GET with randomized delay and retries.

    Hard stops:
    - 403
    - 429
    """

    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

        try:
            resp = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 429:
                log.error(
                    "Rate limited (429) on %s",
                    url,
                )
                # Propagate a requests-compatible HTTPError so callers can handle it
                resp.raise_for_status()

            if resp.status_code == 403:
                log.error(
                    "Blocked (403) on %s",
                    url,
                )
                resp.raise_for_status()

            resp.raise_for_status()
            return resp

        except requests.Timeout:
            log.warning(
                "Timeout on %s (attempt %d/%d), retrying",
                url,
                attempt,
                MAX_RETRIES,
            )

        except requests.RequestException as exc:
            log.warning(
                "Request failed for %s (attempt %d/%d): %s",
                url,
                attempt,
                MAX_RETRIES,
                exc,
            )

    log.warning(
        "Giving up on %s after %d attempts",
        url,
        MAX_RETRIES,
    )

    return None


# ---------------------------------------------------------------------------
# window.state extraction
# ---------------------------------------------------------------------------

def extract_window_state(html: str) -> Optional[dict]:
    match = re.search(r"window\.state\s*=\s*", html)

    if not match:
        return None

    start = match.end()

    depth = 0
    in_string = False
    string_char = ""
    escaped = False
    end = None

    for index in range(start, len(html)):
        ch = html[index]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == string_char:
                in_string = False

            continue

        if ch in ('"', "'"):
            in_string = True
            string_char = ch
            continue

        if ch == "{":
            depth += 1

        elif ch == "}":
            depth -= 1

            if depth == 0:
                end = index + 1
                break

    if end is None:
        return None

    try:
        return json.loads(html[start:end])

    except json.JSONDecodeError as exc:
        log.warning(
            "window.state found but failed to parse as JSON: %s",
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def get_formatted_field(
    hit: dict,
    attribute: str,
) -> Optional[str]:
    """
    Pull a human-readable value from formattedExtraFields.
    """

    for field in hit.get("formattedExtraFields", []):
        if field.get("attribute") == attribute:
            return field.get("formattedValue_l1")

    return None


# ---------------------------------------------------------------------------
# Dubizzle URL resolution
# ---------------------------------------------------------------------------

def _normalize_authoritative_url(
    raw_url: Optional[str],
) -> Optional[str]:

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


def build_ad_url(hit: dict) -> Optional[str]:
    """
    Return an authoritative detail URL only if the source payload contains
    one.

    IMPORTANT:
    We never construct a fake URL from slug + structured ad_id.
    """

    candidates = []

    possible_keys = [
        "ad_url",
        "url",
        "canonical_url",
        "canonicalUrl",
        "listing_url",
        "listingUrl",
        "seo_url",
        "seoUrl",
        "absolute_url",
        "absoluteUrl",
        "canonical",
        "permalink",
        "page_url",
        "pageUrl",
        "href",
        "link",
    ]

    for key in possible_keys:
        value = hit.get(key)

        if isinstance(value, str):
            candidates.append(value)

    def walk(obj):
        if isinstance(obj, dict):

            for key, value in obj.items():

                key_lower = str(key).lower()

                if (
                    isinstance(value, str)
                    and any(
                        token in key_lower
                        for token in (
                            "url",
                            "link",
                            "href",
                            "canonical",
                            "seo",
                            "permalink",
                            "path",
                        )
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

        normalized = _normalize_authoritative_url(candidate)

        if normalized:
            return normalized

    return None


# ---------------------------------------------------------------------------
# DOM listing URL extraction
# ---------------------------------------------------------------------------

_AD_HREF_RE = re.compile(
    r"(?:https?://(?:www\.)?dubizzle\.com\.eg)?"
    r"(?P<path>/+(?:en/)?ad/[^\"'<>\s]+?ID\d+\.html)",
    re.IGNORECASE,
)


def _normalize_match_text(value: object) -> str:

    if value is None:
        return ""

    text = unescape(unquote(str(value)))

    text = text.replace("\u0640", "")

    text = re.sub(
        r"[\u064B-\u065F\u0670]",
        "",
        text,
    )

    text = text.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ى": "ي",
            }
        )
    )

    text = re.sub(
        r"[\u0660-\u0669]",
        lambda match: str(
            ord(match.group()) - 0x0660
        ),
        text,
    )

    text = re.sub(
        r"[^\w\u0600-\u06FF]+",
        " ",
        text,
        flags=re.UNICODE,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip().lower()


def _text_tokens(value: object) -> list[str]:

    text = _normalize_match_text(value)

    return [
        token
        for token in text.split()
        if len(token) >= 2
    ]


def _extract_number(value: object) -> Optional[int]:

    if value is None:
        return None

    raw = _normalize_match_text(value).replace(",", "")

    match = re.search(
        r"\d+(?:\.\d+)?",
        raw,
    )

    if not match:
        return None

    try:
        return int(float(match.group()))

    except (TypeError, ValueError):
        return None


def _hit_match_fields(hit: dict) -> dict:

    price = (
        hit.get("extraFields", {}).get("price")
        or get_formatted_field(hit, "price")
    )

    return {
        "title": hit.get("title") or "",
        "title_tokens": _text_tokens(
            hit.get("title") or ""
        ),
        "price": _extract_number(price),
        "area": _extract_number(
            get_formatted_field(hit, "ft")
        ),
        "bedrooms": _extract_number(
            get_formatted_field(hit, "rooms")
        ),
        "bathrooms": _extract_number(
            get_formatted_field(hit, "bathrooms")
        ),
        "property_type": (
            get_formatted_field(hit, "type")
            or ""
        ),
        "location": (
            hit.get("location.lvl3") or {}
        ).get("name_l1") or "",
        "compound": (
            get_formatted_field(hit, "compound")
            or hit.get("compound")
            or ""
        ),
    }


def _strip_html(value: str) -> str:

    value = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )

    value = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    return unescape(value)


def extract_dom_ad_links(html: str) -> list[dict]:

    results = []
    seen = set()

    for match in _AD_HREF_RE.finditer(html):

        raw_path = match.group("path")

        href = urljoin(
            BASE_URL,
            raw_path,
        )

        if href in seen:
            continue

        seen.add(href)

        window_start = max(
            0,
            match.start() - 4500,
        )

        window_end = min(
            len(html),
            match.end() + 4500,
        )

        context = _strip_html(
            html[window_start:window_end]
        )

        href_unquoted = unquote(href)

        path = urlparse(
            href_unquoted
        ).path

        slug_match = re.search(
            r"/ad/(.+?)-ID\d+\.html$",
            path,
            re.IGNORECASE,
        )

        slug_text = (
            slug_match.group(1).replace("-", " ")
            if slug_match
            else ""
        )

        internal_match = re.search(
            r"-ID(\d+)\.html$",
            path,
            re.IGNORECASE,
        )

        results.append(
            {
                "href": href,
                "slug_text": _normalize_match_text(
                    slug_text
                ),
                "context": _normalize_match_text(
                    context
                ),
                "internal_id": (
                    internal_match.group(1)
                    if internal_match
                    else None
                ),
            }
        )

    return results


def _candidate_score(
    fields: dict,
    candidate: dict,
) -> tuple[float, dict]:

    candidate_text = candidate.get(
        "context",
        "",
    )

    candidate_slug = candidate.get(
        "slug_text",
        "",
    )

    title_tokens = fields["title_tokens"]

    if not title_tokens:
        return 0.0, {}

    title_matches = sum(
        1
        for token in title_tokens
        if (
            token in candidate_slug
            or token in candidate_text
        )
    )

    title_coverage = (
        title_matches / max(len(title_tokens), 1)
    )

    hit_title = fields["title"]

    slug_ratio = SequenceMatcher(
        None,
        _normalize_match_text(hit_title),
        candidate_slug,
    ).ratio()

    score = (
        0.55 * title_coverage
        + 0.20 * slug_ratio
    )

    evidence = {
        "title_coverage": round(
            title_coverage,
            4,
        ),
        "slug_ratio": round(
            slug_ratio,
            4,
        ),
    }

    numeric_specs = [
        ("price", 0.12),
        ("area", 0.06),
        ("bedrooms", 0.03),
        ("bathrooms", 0.03),
    ]

    for field_name, weight in numeric_specs:

        expected = fields.get(
            field_name
        )

        if expected is None:
            continue

        if re.search(
            rf"\b{re.escape(str(expected))}\b",
            candidate_text,
        ):
            score += weight
            evidence[field_name] = True
        else:
            evidence[field_name] = False

    location_parts = _text_tokens(
        fields.get("location") or ""
    )

    compound_parts = _text_tokens(
        fields.get("compound") or ""
    )

    geo_tokens = (
        location_parts
        + compound_parts
    )

    if geo_tokens:

        geo_hits = sum(
            1
            for token in set(geo_tokens)
            if token in candidate_text
        )

        geo_coverage = (
            geo_hits
            / len(set(geo_tokens))
        )

        score += (
            0.10
            * min(geo_coverage, 1.0)
        )

        evidence["geo_coverage"] = round(
            geo_coverage,
            4,
        )

    return score, evidence


def resolve_dom_ad_urls(
    hits: list[dict],
    html: str,
) -> dict[str, str]:

    """
    Match structured hits to real /ad/ hrefs rendered by Dubizzle.
    """

    dom_links = extract_dom_ad_links(html)

    if not dom_links:
        log.warning(
            "No real /ad/ anchors found in rendered search HTML"
        )
        return {}

    resolved = {}
    used_hrefs = set()

    for hit in hits:

        hit_id = str(
            hit.get("id")
            or hit.get("objectID")
            or ""
        ).strip()

        if not hit_id:
            continue

        direct = build_ad_url(hit)

        if direct:
            resolved[hit_id] = direct
            used_hrefs.add(direct)
            continue

        fields = _hit_match_fields(hit)

        ranked = []

        for candidate in dom_links:

            if candidate["href"] in used_hrefs:
                continue

            score, evidence = _candidate_score(
                fields,
                candidate,
            )

            ranked.append(
                (
                    score,
                    candidate,
                    evidence,
                )
            )

        ranked.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        if not ranked:
            continue

        best_score, best_candidate, best_evidence = ranked[0]

        second_score = (
            ranked[1][0]
            if len(ranked) > 1
            else 0.0
        )

        margin = (
            best_score - second_score
        )

        title_ok = (
            best_evidence.get(
                "title_coverage",
                0.0,
            ) >= 0.50
            or
            best_evidence.get(
                "slug_ratio",
                0.0,
            ) >= 0.72
        )

        sufficiently_separated = (
            margin >= 0.06
            or
            best_score >= 0.86
        )

        if (
            best_score >= 0.62
            and title_ok
            and sufficiently_separated
        ):
            resolved[hit_id] = (
                best_candidate["href"]
            )

            used_hrefs.add(
                best_candidate["href"]
            )

            log.debug(
                "Resolved ad URL: hit_id=%s -> %s "
                "(score=%.3f margin=%.3f evidence=%s)",
                hit_id,
                best_candidate["href"],
                best_score,
                margin,
                best_evidence,
            )

        else:
            log.debug(
                "Ambiguous/unmatched ad URL: "
                "hit_id=%s best=%s score=%.3f "
                "margin=%.3f evidence=%s",
                hit_id,
                best_candidate.get("href"),
                best_score,
                margin,
                best_evidence,
            )

    log.info(
        "Resolved %d/%d structured hits to real Dubizzle ad URLs",
        len(resolved),
        len(hits),
    )

    return resolved


def validate_ad_url(
    url: str,
    expected_ad_id: str,
    expected_title: Optional[str] = None,
) -> bool | None:

    """
    Validate a resolved real ad URL.

    We intentionally do not require the structured ad_id to appear in
    the public URL because Dubizzle can expose a different internal
    public route ID.
    """

    try:

        resp = polite_get(url)

        if resp is None:
            return None

        text = resp.text

        if not re.search(
            r"/ad/",
            str(resp.url),
            re.IGNORECASE,
        ):
            return False

        if expected_title:

            title_norm = _normalize_match_text(
                expected_title
            )

            page_norm = _normalize_match_text(
                text
            )

            title_tokens = _text_tokens(
                title_norm
            )

            if title_tokens:

                matches = sum(
                    1
                    for token in title_tokens
                    if token in page_norm
                )

                coverage = (
                    matches
                    / len(title_tokens)
                )

                if coverage < 0.35:
                    return False

        return True

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Compound extraction
# ---------------------------------------------------------------------------

COMPOUND_CHOICES: list[dict] = []


def load_compound_choices(
    path: Path = Path("window_state.json"),
) -> list:

    choices = []

    if not path.exists():
        return choices

    try:

        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        found = []

        def walk(obj):

            if isinstance(obj, dict):

                if (
                    obj.get("attribute")
                    == "compound"
                    and "choices" in obj
                ):
                    found.append(
                        obj["choices"]
                    )

                for value in obj.values():
                    walk(value)

            elif isinstance(obj, list):

                for item in obj:
                    walk(item)

        walk(data)

        if found:
            choices = found[0]

    except Exception:
        return []

    return choices


COMPOUND_CHOICES = load_compound_choices()


def _detect_compound_from_text(
    text: str,
) -> Optional[str]:

    if not text:
        return None

    text_lower = text.lower()

    best = None
    best_len = 0

    for choice in COMPOUND_CHOICES:

        label = (
            choice.get("label")
            or choice.get("name")
            or ""
        )

        if not label:
            continue

        if (
            label.lower() in text_lower
            and len(label) > best_len
        ):
            best = label
            best_len = len(label)

    return best


# ---------------------------------------------------------------------------
# Listing normalization
# ---------------------------------------------------------------------------

def normalize_hit(
    hit: dict,
    listing_type: str,
    resolved_ad_url: Optional[str] = None,
) -> Optional[Listing]:

    try:

        ad_id = str(
            hit.get("id")
            or hit.get("objectID")
        )

        if (
            not ad_id
            or ad_id == "None"
        ):
            return None

        # Only active source listings qualify.
        if (
            hit.get("state")
            and hit.get("state") != "active"
        ):
            return None

        scraped_at = datetime.now(
            timezone.utc
        )

        updated_ts = (
            hit.get("updatedAt")
            or hit.get("createdAt")
        )

        days_since_updated = None

        if updated_ts:

            days_since_updated = (
                scraped_at
                - datetime.fromtimestamp(
                    updated_ts,
                    tz=timezone.utc,
                )
            ).days

            days_since_updated = max(
                0,
                days_since_updated,
            )

        description = (
            hit.get("description")
            or ""
        )

        phone_match = PHONE_PATTERN.search(
            description
        )

        agency = hit.get("agency")

        location_l3 = (
            hit.get("location.lvl3")
            or {}
        )

        geo = (
            hit.get("geography")
            or {}
        )

        contact = (
            hit.get("contactInfo")
            or {}
        )

        amenities_field = get_formatted_field(
            hit,
            "features",
        )

        amenities_str = (
            ", ".join(amenities_field)
            if isinstance(amenities_field, list)
            else amenities_field
        )

        price = (
            hit.get("extraFields", {}).get(
                "price"
            )
            or get_formatted_field(
                hit,
                "price",
            )
        )

        compound_val = (
            get_formatted_field(
                hit,
                "compound",
            )
            or hit.get("compound")
            or None
        )

        if not compound_val:

            text_source = " ".join(
                filter(
                    None,
                    [
                        hit.get("title", ""),
                        hit.get(
                            "description",
                            "",
                        ),
                        hit.get(
                            "external_link",
                            "",
                        ),
                    ],
                )
            )

            compound_val = (
                _detect_compound_from_text(
                    text_source
                )
            )

        return Listing(
            ad_id=ad_id,
            ad_url=(
                resolved_ad_url
                or build_ad_url(hit)
            ),
            listing_type=listing_type,
            property_type=get_formatted_field(
                hit,
                "type",
            ),
            title=hit.get("title"),
            price=(
                str(price)
                if price is not None
                else None
            ),
            area_sqm=get_formatted_field(
                hit,
                "ft",
            ),
            bedrooms=get_formatted_field(
                hit,
                "rooms",
            ),
            bathrooms=get_formatted_field(
                hit,
                "bathrooms",
            ),
            completion_status=get_formatted_field(
                hit,
                "completion_status",
            ),
            payment_method=get_formatted_field(
                hit,
                "payment_option",
            ),
            ownership=get_formatted_field(
                hit,
                "ownership",
            ),
            furnished=get_formatted_field(
                hit,
                "furnished",
            ),
            location_text=location_l3.get(
                "name_l1"
            ),
            compound=compound_val,
            location_link=(
                f"https://www.google.com/maps"
                f"?q={geo['lat']},{geo['lng']}"
                if (
                    "lat" in geo
                    and "lng" in geo
                )
                else None
            ),
            amenities=amenities_str,
            description_full=description,
            phone_in_description=(
                phone_match.group(0)
                if phone_match
                else None
            ),
            posted_at=(
                datetime.fromtimestamp(
                    hit["createdAt"],
                    tz=timezone.utc,
                ).isoformat()
                if hit.get("createdAt")
                else None
            ),
            updated_at=(
                datetime.fromtimestamp(
                    updated_ts,
                    tz=timezone.utc,
                ).isoformat()
                if updated_ts
                else None
            ),
            scraped_at=scraped_at.isoformat(),
            days_since_updated=days_since_updated,
            is_verified_business=bool(
                hit.get("isSellerVerified", False)
            ),
            is_agency=agency is not None,
            agency_name=(
                agency.get("name")
                if agency
                else None
            ),
            has_broker_code_pattern=bool(
                BROKER_CODE_PATTERN.search(
                    description
                )
            ),
            seller_id=hit.get(
                "userExternalID"
            ),
            seller_name=contact.get(
                "name"
            ),
        )

    except Exception as exc:

        log.warning(
            "Failed to normalize a hit (id=%s): %s",
            hit.get("id"),
            exc,
        )

        return None


# ---------------------------------------------------------------------------
# Search scraping
# ---------------------------------------------------------------------------

def scrape_search_results(
    base_url: str,
    listing_type: str,
) -> list[Listing]:

    all_listings = []

    seen_first_hit_id = None

    for page in range(
        1,
        MAX_PAGES + 1,
    ):

        url = (
            base_url
            if page == 1
            else f"{base_url}?page={page}"
        )

        resp = polite_get(url)

        if resp is None:

            log.warning(
                "Skipping page %d for %s "
                "(request failed)",
                page,
                listing_type,
            )

            continue

        state = extract_window_state(
            resp.text
        )

        if state is None:

            log.error(
                "No window.state found on page %d "
                "of %s - stopping this category",
                page,
                listing_type,
            )

            break

        content = (
            state
            .get("algolia", {})
            .get("content", {})
        )

        hits = content.get(
            "hits",
            [],
        )

        if not hits:

            log.info(
                "No hits on page %d of %s - "
                "assuming end of results",
                page,
                listing_type,
            )

            break

        first_id = hits[0].get("id")

        if page == 1:

            seen_first_hit_id = first_id

        elif first_id == seen_first_hit_id:

            log.warning(
                "Page %d returned the same first hit "
                "as page 1 for %s - pagination is "
                "likely wrong, stopping category",
                page,
                listing_type,
            )

            break

        resolved_urls = resolve_dom_ad_urls(
            hits,
            resp.text,
        )

        listings = [
            normalize_hit(
                hit,
                listing_type,
                resolved_ad_url=resolved_urls.get(
                    str(
                        hit.get("id")
                        or hit.get("objectID")
                        or ""
                    )
                ),
            )
            for hit in hits
        ]

        listings = [
            listing
            for listing in listings
            if listing is not None
        ]

        matched = sum(
            1
            for listing in listings
            if listing.ad_url
        )

        log.info(
            "Page %d of %s: resolved %d/%d "
            "listings to real Dubizzle URLs",
            page,
            listing_type,
            matched,
            len(listings),
        )

        fresh = [
            listing
            for listing in listings
            if (
                listing.days_since_updated is None
                or listing.days_since_updated
                <= FRESHNESS_DAYS
            )
        ]

        stale_count = (
            len(listings)
            - len(fresh)
        )

        all_listings.extend(
            fresh
        )

        log.info(
            "Page %d of %s: %d listings "
            "(%d fresh, %d older than %d days, dropped)",
            page,
            listing_type,
            len(listings),
            len(fresh),
            stale_count,
            FRESHNESS_DAYS,
        )

        if (
            listings
            and stale_count == len(listings)
        ):

            log.info(
                "Entire page %d of %s was older "
                "than %d days - stopping category",
                page,
                listing_type,
                FRESHNESS_DAYS,
            )

            break

        nb_pages_reported = content.get(
            "nbPages"
        )

        if (
            nb_pages_reported
            and page >= nb_pages_reported
        ):
            break

    return all_listings


# ---------------------------------------------------------------------------
# Seller cache
# ---------------------------------------------------------------------------

def build_profile_url(
    seller_id: str,
) -> str:

    return (
        f"{BASE_URL}/en/profile/"
        f"{seller_id}/"
    )


def load_sellers_cache() -> dict[str, dict]:

    """
    Persistent seller cache.

    Existing sellers are loaded and retained across runs.
    """

    if not SELLERS_CSV.exists():
        return {}

    with open(
        SELLERS_CSV,
        newline="",
        encoding="utf-8",
    ) as file:

        rows = list(
            csv.DictReader(file)
        )

    output = {}

    for row in rows:

        seller_id = row.get(
            "seller_id"
        )

        if not seller_id:
            continue

        if (
            "active_ads_count_source"
            not in row
        ):
            row[
                "active_ads_count_source"
            ] = ""

        if (
            "profile_url"
            not in row
            or not row.get("profile_url")
        ):
            row["profile_url"] = (
                build_profile_url(
                    seller_id
                )
            )

        output[seller_id] = row

    return output


def save_sellers_cache(
    cache: dict[str, dict],
) -> None:

    """
    Persist the COMPLETE seller cache.

    This function rewrites the CSV physically, but it does NOT replace
    the cache with only the current run. It writes every existing seller
    plus any new/updated seller.

    Therefore:
    - old sellers remain
    - permanent blacklist remains
    - owner/broker classification remains
    - new sellers are added
    """

    fieldnames = [
        "seller_id",
        "seller_name",
        "profile_url",
        "active_ads_count",
        "active_ads_count_source",
        "classification",
        "checked_at",
        "blocklist_permanent",
    ]

    DATA_DIR.mkdir(
        exist_ok=True
    )

    with open(
        SELLERS_CSV,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for row in cache.values():

            seller_id = row.get(
                "seller_id",
                "",
            )

            output_row = {
                "seller_id": seller_id,
                "seller_name": row.get(
                    "seller_name",
                    "",
                ),
                "profile_url": (
                    row.get("profile_url")
                    or build_profile_url(
                        seller_id
                    )
                ),
                "active_ads_count": row.get(
                    "active_ads_count",
                    "",
                ),
                "active_ads_count_source": row.get(
                    "active_ads_count_source",
                    "",
                ),
                "classification": row.get(
                    "classification",
                    "",
                ),
                "checked_at": row.get(
                    "checked_at",
                    "",
                ),
                "blocklist_permanent": row.get(
                    "blocklist_permanent",
                    "False",
                ),
            }

            writer.writerow(
                output_row
            )


def needs_profile_check(
    seller_id: str,
    listing: Listing,
    cache: dict,
) -> bool:

    if listing.is_agency:
        return False

    entry = cache.get(
        seller_id
    )

    if entry is None:
        return True

    if (
        entry.get(
            "blocklist_permanent"
        )
        == "True"
    ):
        return False

    if (
        entry.get(
            "active_ads_count_source"
        )
        != "seller_profile"
    ):
        return True

    checked_at = entry.get(
        "checked_at"
    )

    if not checked_at:
        return True

    try:

        age = (
            datetime.now(
                timezone.utc
            )
            - datetime.fromisoformat(
                checked_at
            )
        )

    except ValueError:

        return True

    return age > timedelta(
        days=OWNER_RECHECK_DAYS
    )


# ---------------------------------------------------------------------------
# Seller profile extraction
# ---------------------------------------------------------------------------

def check_seller_profile(
    seller_id: str,
) -> Optional[int]:

    """
    Visit the REAL seller profile and extract an explicit ad count.

    We never default missing values to zero.
    """

    profile_url = build_profile_url(
        seller_id
    )

    resp = polite_get(
        profile_url
    )

    if resp is None:
        return None

    state = extract_window_state(
        resp.text
    )

    if state is None:

        log.warning(
            "Could not extract profile page data "
            "for seller_id=%s",
            seller_id,
        )

        return None

    seller_profile = (
        state.get(
            "sellerProfile"
        )
        if isinstance(state, dict)
        else None
    )

    if not isinstance(
        seller_profile,
        dict,
    ):
        return None

    data = (
        seller_profile.get("data")
        if isinstance(
            seller_profile.get("data"),
            dict,
        )
        else None
    )

    # Production-observed location.
    if (
        data
        and "adsCount" in data
    ):

        try:

            value = data.get(
                "adsCount"
            )

            if value is None:
                return None

            return int(value)

        except (
            TypeError,
            ValueError,
        ):

            return None

    # Conservative fallbacks.
    for key in (
        "activeAdsCount",
        "adsCount",
        "activeAds",
    ):

        if key not in seller_profile:
            continue

        try:

            value = seller_profile.get(
                key
            )

            if value is None:
                return None

            return int(value)

        except (
            TypeError,
            ValueError,
        ):

            return None

    return None


def _find_seller_profile_in_state(
    obj,
    seller_id: str,
):

    """
    Recursively search window.state for seller profile information
    belonging to the requested seller.
    """

    if isinstance(obj, dict):

        seller_profile = obj.get(
            "sellerProfile"
        )

        if isinstance(
            seller_profile,
            dict,
        ):

            seller_profile_id = (
                seller_profile.get(
                    "sellerId"
                )
                or seller_profile.get(
                    "id"
                )
                or seller_profile.get(
                    "userId"
                )
            )

            data = (
                seller_profile.get(
                    "data"
                )
                if isinstance(
                    seller_profile.get(
                        "data"
                    ),
                    dict,
                )
                else None
            )

            if (
                not seller_profile_id
                and data
            ):
                seller_profile_id = (
                    data.get(
                        "externalID"
                    )
                    or data.get(
                        "externalId"
                    )
                    or data.get("id")
                )

            if (
                not seller_id
                or (
                    seller_profile_id
                    and str(
                        seller_profile_id
                    )
                    == str(seller_id)
                )
            ):

                if (
                    data
                    and "adsCount" in data
                ):

                    try:

                        value = data.get(
                            "adsCount"
                        )

                        if value is None:
                            return None

                        return int(value)

                    except (
                        TypeError,
                        ValueError,
                    ):

                        return None

                for key in (
                    "activeAdsCount",
                    "adsCount",
                ):

                    if key in seller_profile:

                        try:

                            value = seller_profile.get(
                                key
                            )

                            if value is None:
                                return None

                            return int(value)

                        except (
                            TypeError,
                            ValueError,
                        ):

                            return None

        for value in obj.values():

            found = (
                _find_seller_profile_in_state(
                    value,
                    seller_id,
                )
            )

            if found is not None:
                return found

    elif isinstance(obj, list):

        for item in obj:

            found = (
                _find_seller_profile_in_state(
                    item,
                    seller_id,
                )
            )

            if found is not None:
                return found

    return None


def check_listing_for_seller_count(
    listing: Listing,
) -> Optional[int]:

    """
    Fallback:
    inspect listing page window.state for seller profile count.
    """

    if not listing.ad_url:
        return None

    try:

        resp = polite_get(
            listing.ad_url
        )

        if resp is None:
            return None

        state = extract_window_state(
            resp.text
        )

        if state is None:
            return None

        return _find_seller_profile_in_state(
            state,
            listing.seller_id,
        )

    except Exception:

        return None


# ---------------------------------------------------------------------------
# Broker detection
# ---------------------------------------------------------------------------

def apply_broker_detection(
    listings: list[Listing],
    cache: dict,
) -> None:

    seller_counts = {}

    for listing in listings:

        if listing.seller_id:

            seller_counts[
                listing.seller_id
            ] = (
                seller_counts.get(
                    listing.seller_id,
                    0,
                )
                + 1
            )

    for listing in listings:

        if listing.seller_id:

            listing.seller_repeat_count = (
                seller_counts[
                    listing.seller_id
                ]
            )

    checked_this_run = set()

    for listing in listings:

        seller_id = listing.seller_id

        if (
            not seller_id
            or seller_id in checked_this_run
        ):
            continue

        checked_this_run.add(
            seller_id
        )

        if not needs_profile_check(
            seller_id,
            listing,
            cache,
        ):
            continue

        profile_url = build_profile_url(
            seller_id
        )

        # PRIMARY:
        # Visit seller profile.
        active_count = (
            check_seller_profile(
                seller_id
            )
        )

        active_count_source = None

        if active_count is not None:
            active_count_source = (
                "seller_profile"
            )

        # FALLBACK:
        # Listing page state.
        if active_count is None:

            listing_count = (
                check_listing_for_seller_count(
                    listing
                )
            )

            if listing_count is not None:

                active_count = (
                    listing_count
                )

                active_count_source = (
                    "listing_window_state"
                )

        # Do NOT destroy previous trusted classification
        # if current lookup failed.
        if active_count is None:

            log.info(
                "Seller check for %s returned "
                "no usable activeAdsCount",
                seller_id,
            )

            continue

        is_broker = (
            active_count
            > BROKER_ACTIVE_ADS_THRESHOLD
        )

        # Preserve/update seller cache.
        cache[seller_id] = {
            "seller_id": seller_id,
            "seller_name": (
                listing.seller_name
                or ""
            ),
            "profile_url": profile_url,
            "active_ads_count": str(
                active_count
            ),
            "active_ads_count_source": (
                active_count_source
                or ""
            ),
            "classification": (
                "broker"
                if is_broker
                else "owner"
            ),
            "checked_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            "blocklist_permanent": str(
                is_broker
            ),
        }

        log.info(
            "Checked seller_id=%s (%s) "
            "-> active_ads=%d -> %s "
            "(source=%s)",
            seller_id,
            listing.seller_name,
            active_count,
            (
                "broker"
                if is_broker
                else "owner"
            ),
            active_count_source,
        )


# ---------------------------------------------------------------------------
# Historical listings persistence
# ---------------------------------------------------------------------------

def load_existing_ads() -> dict[str, dict]:

    if not ADS_CSV.exists():
        return {}

    with open(
        ADS_CSV,
        newline="",
        encoding="utf-8",
    ) as file:

        rows = csv.DictReader(file)

        return {
            row["ad_id"]: row
            for row in rows
            if row.get("ad_id")
        }


def merge_and_save(
    new_listings: list[Listing],
) -> None:

    """
    Historical upsert.

    Existing listings are preserved.
    New listings are added.
    Existing listings are updated by ad_id.

    IMPORTANT:
    Physically the CSV file is rewritten, but the dataset itself
    is cumulative because we first load all existing rows and merge
    the new run into them.
    """

    today = datetime.now(
        timezone.utc
    ).date().isoformat()

    existing = load_existing_ads()

    seen_today_ids = set()

    for listing in new_listings:

        seen_today_ids.add(
            listing.ad_id
        )

        row = asdict(
            listing
        )

        prior = existing.get(
            listing.ad_id
        )

        row["first_seen_date"] = (
            prior.get(
                "first_seen_date"
            )
            if prior
            else today
        )

        row["last_seen_date"] = today

        row["is_active"] = True

        # Never accidentally overwrite an old valid URL
        # with an empty URL if current resolution failed.
        if listing.ad_url:

            row["ad_url"] = (
                listing.ad_url
            )

        elif prior:

            row["ad_url"] = (
                prior.get(
                    "ad_url",
                    "",
                )
            )

        else:

            row["ad_url"] = ""

        existing[
            listing.ad_id
        ] = {
            key: (
                ""
                if value is None
                else str(value)
            )
            for key, value in row.items()
        }

    # Important:
    # We preserve historical rows.
    # We mark rows not seen in this run inactive.
    for ad_id, row in existing.items():

        if ad_id not in seen_today_ids:

            row["is_active"] = "False"

    DATA_DIR.mkdir(
        exist_ok=True
    )

    with open(
        ADS_CSV,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=ALL_FIELDS,
        )

        writer.writeheader()

        for row in existing.values():

            writer.writerow(
                {
                    key: row.get(
                        key,
                        "",
                    )
                    for key in ALL_FIELDS
                }
            )

    log.info(
        "Saved historical listings: "
        "%d total (%d seen/updated this run)",
        len(existing),
        len(seen_today_ids),
    )


# ---------------------------------------------------------------------------
# Sellers cache migration
# ---------------------------------------------------------------------------

def migrate_sellers_cache(
    path: Path = SELLERS_CSV,
) -> dict:

    """
    Migrate old seller cache rows.

    Unproven zero counts are converted to unknown.

    Classification is preserved.
    """

    summary = {
        "total": 0,
        "zeros_before": 0,
        "positive_before": 0,
        "null_before": 0,
        "with_provenance_before": 0,
        "zeros_migrated": 0,
    }

    if not path.exists():
        return summary

    with open(
        path,
        newline="",
        encoding="utf-8",
    ) as file:

        rows = list(
            csv.DictReader(file)
        )

    summary["total"] = len(rows)

    output_rows = []

    for row in rows:

        active_count = (
            row.get(
                "active_ads_count"
            )
            or ""
        )

        source = (
            row.get(
                "active_ads_count_source"
            )
            if (
                "active_ads_count_source"
                in row
            )
            else ""
        )

        if active_count.strip() == "0":

            summary["zeros_before"] += 1

        elif not active_count.strip():

            summary["null_before"] += 1

        else:

            try:

                if (
                    int(float(active_count))
                    > 0
                ):
                    summary[
                        "positive_before"
                    ] += 1

            except Exception:

                summary[
                    "null_before"
                ] += 1

        if (
            source
            and source.strip()
        ):
            summary[
                "with_provenance_before"
            ] += 1

        if (
            active_count.strip() == "0"
            and not source.strip()
        ):

            row[
                "active_ads_count"
            ] = ""

            row[
                "active_ads_count_source"
            ] = "unknown"

            summary[
                "zeros_migrated"
            ] += 1

        else:

            row.setdefault(
                "active_ads_count_source",
                source or "",
            )

        output_rows.append(
            row
        )

    fieldnames = [
        "seller_id",
        "seller_name",
        "profile_url",
        "active_ads_count",
        "active_ads_count_source",
        "classification",
        "checked_at",
        "blocklist_permanent",
    ]

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for row in output_rows:

            row = dict(row)

            row.setdefault(
                "profile_url",
                build_profile_url(
                    row.get(
                        "seller_id",
                        "",
                    )
                ),
            )

            writer.writerow(
                {
                    key: row.get(
                        key,
                        "",
                    )
                    for key in fieldnames
                }
            )

    return summary


# ---------------------------------------------------------------------------
# Business dataset generation
# ---------------------------------------------------------------------------

def generate_business_dataset(
    listings_csv: Path = ADS_CSV,
    sellers_csv: Path = SELLERS_CSV,
    out_csv: Path = BUSINESS_CSV,
    freshness_days: int = FRESHNESS_DAYS,
) -> None:

    """
    Build the CURRENT business-facing snapshot.

    This intentionally does NOT accumulate historical business rows.

    Historical data lives in listings.csv.

    Business dataset includes only listings that are:
    - active
    - fresh
    - not agency/company
    - seller known
    - seller not permanently blacklisted
    - seller classification trusted
    - seller classified as owner
    """

    if not listings_csv.exists():

        log.error(
            "Listings CSV not found, "
            "cannot generate business dataset"
        )

        return

    sellers = {}

    if sellers_csv.exists():

        with open(
            sellers_csv,
            newline="",
            encoding="utf-8",
        ) as file:

            for row in csv.DictReader(
                file
            ):

                seller_id = row.get(
                    "seller_id"
                )

                if seller_id:
                    sellers[seller_id] = row

    included = []

    with open(
        listings_csv,
        newline="",
        encoding="utf-8",
    ) as file:

        reader = csv.DictReader(
            file
        )

        for row in reader:

            try:

                # Only current active listings.
                if row.get(
                    "is_active",
                    "False",
                ) not in (
                    "True",
                    "true",
                    "1",
                ):
                    continue

                # Exclude agency/company listings.
                if row.get(
                    "is_agency",
                    "False",
                ) in (
                    "True",
                    "true",
                    "1",
                ):
                    continue

                # Freshness filter.
                days = row.get(
                    "days_since_updated"
                )

                if days:

                    try:

                        if (
                            int(days)
                            > freshness_days
                        ):
                            continue

                    except ValueError:
                        pass

                seller_id = row.get(
                    "seller_id"
                )

                if not seller_id:
                    continue

                seller = sellers.get(
                    seller_id
                )

                if not seller:
                    continue

                # Permanent blacklist.
                if (
                    seller.get(
                        "blocklist_permanent"
                    )
                    == "True"
                ):
                    continue

                # Classification freshness.
                trusted = False

                checked_at = seller.get(
                    "checked_at"
                )

                if checked_at:

                    try:

                        checked_dt = (
                            datetime.fromisoformat(
                                checked_at
                            )
                        )

                        age_days = (
                            datetime.now(
                                timezone.utc
                            )
                            - checked_dt
                        ).days

                        if (
                            age_days
                            <= OWNER_RECHECK_DAYS
                        ):
                            trusted = True

                    except Exception:

                        trusted = False

                if not trusted:
                    continue

                # Must be owner.
                if (
                    seller.get(
                        "classification"
                    )
                    != "owner"
                ):
                    continue

                active_ads_count = (
                    seller.get(
                        "active_ads_count"
                    )
                    or ""
                )

                out_row = {
                    "ad_id": row.get(
                        "ad_id"
                    ),
                    "ad_url": row.get(
                        "ad_url"
                    ),
                    "listing_type": row.get(
                        "listing_type"
                    ),
                    "title": row.get(
                        "title"
                    ),
                    "price": row.get(
                        "price"
                    ),
                    "area_sqm": row.get(
                        "area_sqm"
                    ),
                    "bedrooms": row.get(
                        "bedrooms"
                    ),
                    "bathrooms": row.get(
                        "bathrooms"
                    ),
                    "property_type": row.get(
                        "property_type"
                    ),
                    "completion_status": row.get(
                        "completion_status"
                    ),
                    "payment_method": row.get(
                        "payment_method"
                    ),
                    "furnished": row.get(
                        "furnished"
                    ),
                    "location_text": row.get(
                        "location_text"
                    ),
                    "compound": row.get(
                        "compound"
                    ),
                    "description_full": row.get(
                        "description_full"
                    ),
                    "posted_at": row.get(
                        "posted_at"
                    ),
                    "updated_at": row.get(
                        "updated_at"
                    ),
                    "days_since_updated": row.get(
                        "days_since_updated"
                    ),
                    "seller_name": (
                        seller.get(
                            "seller_name"
                        )
                        or row.get(
                            "seller_name"
                        )
                    ),
                    "active_ads_count": (
                        active_ads_count
                    ),
                    "likely_owner": "True",
                }

                included.append(
                    out_row
                )

            except Exception as exc:

                log.warning(
                    "Skipping row while "
                    "generating business dataset: %s",
                    exc,
                )

    DATA_DIR.mkdir(
        exist_ok=True
    )

    with open(
        out_csv,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=BUSINESS_FIELDS,
        )

        writer.writeheader()

        for row in included:
            writer.writerow(row)

    log.info(
        "Generated CURRENT business dataset "
        "with %d eligible listings -> %s",
        len(included),
        str(out_csv),
    )

def save_scrape_status(
    scraped_listings: int,
    business_listings: int,
    sellers_count: int,
) -> None:
    """
    Persist metadata about the latest COMPLETED scraper run.

    This timestamp represents the successful completion of the full
    pipeline, not merely the time at which individual listings were fetched.
    """

    DATA_DIR.mkdir(exist_ok=True)

    payload = {
        "status": "success",
        "last_successful_scrape_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "scraped_listings": int(
            scraped_listings
        ),
        "business_listings": int(
            business_listings
        ),
        "sellers_count": int(
            sellers_count
        ),
    }

    tmp_path = SCRAPE_STATUS_JSON.with_suffix(
        ".json.tmp"
    )

    tmp_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp_path.replace(
        SCRAPE_STATUS_JSON
    )

    log.info(
        "Saved scrape status -> %s",
        SCRAPE_STATUS_JSON,
    )


def save_failed_scrape_status(reason: str) -> None:
    """
    Write a failure scrape_status.json with partial counts derived from
    existing data files so the uploader can capture the failure.
    """
    DATA_DIR.mkdir(exist_ok=True)

    def _count_csv(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                return sum(1 for _ in csv.DictReader(fh))
        except Exception:
            return 0

    payload = {
        "status": "failed",
        "last_attempt_scrape_at": datetime.now(timezone.utc).isoformat(),
        "reason": str(reason),
        "scraped_listings": _count_csv(ADS_CSV),
        "business_listings": _count_csv(BUSINESS_CSV),
        "sellers_count": _count_csv(SELLERS_CSV),
    }

    tmp_path = SCRAPE_STATUS_JSON.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(SCRAPE_STATUS_JSON)
    log.info("Saved failed scrape status -> %s", SCRAPE_STATUS_JSON)
# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------

def print_run_summary(
    scraped_count: int,
    cache: dict,
) -> None:

    try:

        historical = load_existing_ads()

        active_historical = sum(
            1
            for row in historical.values()
            if row.get("is_active")
            in (
                "True",
                "true",
                "1",
                True,
            )
        )

        blacklisted = sum(
            1
            for row in cache.values()
            if row.get(
                "blocklist_permanent"
            )
            == "True"
        )

        owners = sum(
            1
            for row in cache.values()
            if row.get(
                "classification"
            )
            == "owner"
        )

        brokers = sum(
            1
            for row in cache.values()
            if row.get(
                "classification"
            )
            == "broker"
        )

        log.info(
            "RUN SUMMARY: scraped=%d, "
            "historical_total=%d, "
            "historical_active=%d, "
            "sellers=%d, owners=%d, "
            "brokers=%d, blacklist=%d",
            scraped_count,
            len(historical),
            active_historical,
            len(cache),
            owners,
            brokers,
            blacklisted,
        )

    except Exception as exc:

        log.warning(
            "Could not build run summary: %s",
            exc,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    
    DATA_DIR.mkdir(exist_ok=True)

    all_listings: list[Listing] = []

    # -------------------------------------------------------
    # 1. Scrape all configured listing categories
    # -------------------------------------------------------

    for listing_type, url in SEARCH_URLS.items():

        log.info(
            "Scraping %s listings from %s "
            "(max %d pages)",
            listing_type,
            url,
            MAX_PAGES,
        )

        listings = scrape_search_results(
            url,
            listing_type,
        )

        log.info(
            "Got %d %s listings total",
            len(listings),
            listing_type,
        )

        all_listings.extend(
            listings
        )

    if not all_listings:
        log.error(
            "No listings extracted at all - "
            "not saving anything"
        )
        raise SystemExit(1)

    # -------------------------------------------------------
    # 2. Load persistent seller cache
    # -------------------------------------------------------

    cache = load_sellers_cache()

    # -------------------------------------------------------
    # 3. Update seller classification/counts
    # -------------------------------------------------------

    apply_broker_detection(
        all_listings,
        cache,
    )

    # -------------------------------------------------------
    # 4. Persist complete seller cache
    # -------------------------------------------------------

    save_sellers_cache(
        cache
    )

    # -------------------------------------------------------
    # 5. Merge into historical listing dataset
    # -------------------------------------------------------

    merge_and_save(
        all_listings
    )

    # -------------------------------------------------------
    # 6. Rebuild CURRENT business-facing snapshot
    # -------------------------------------------------------

    try:

        generate_business_dataset()

    except Exception as exc:

        log.error(
            "Failed to generate business dataset: %s",
            exc,
        )

        raise SystemExit(1)

    # -------------------------------------------------------
    # 7. Validate business output
    # -------------------------------------------------------

    out_csv = (
        DATA_DIR /
        "business_listings.csv"
    )

    if (
        not out_csv.exists()
        or out_csv.stat().st_size == 0
    ):

        log.error(
            "Business dataset generation failed "
            "or produced empty file: %s",
            out_csv,
        )

        raise SystemExit(1)

    # -------------------------------------------------------
    # 8. Count current business listings
    # -------------------------------------------------------

    try:

        with open(
            out_csv,
            newline="",
            encoding="utf-8",
        ) as file:

            business_count = sum(
                1
                for _ in csv.DictReader(
                    file
                )
            )

    except Exception as exc:

        log.error(
            "Could not inspect business dataset: %s",
            exc,
        )

        raise SystemExit(1)

    # -------------------------------------------------------
    # 9. ONLY NOW mark the run successful
    # -------------------------------------------------------

    save_scrape_status(
        scraped_listings=len(
            all_listings
        ),
        business_listings=business_count,
        sellers_count=len(
            cache
        ),
    )

    log.info(
        "Scraper run completed successfully."
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log.exception("Scraper execution failed: %s", exc)
        try:
            save_failed_scrape_status(str(exc))
        except Exception as inner_exc:
            log.exception("Failed to persist failed scrape status: %s", inner_exc)
        raise SystemExit(1)
