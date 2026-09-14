from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class NormalizedListing:
    """Source-neutral listing object used by shared API/store logic.

    This model deliberately holds only shared real-estate concepts.
    Source-specific details stay outside.
    """

    source: str
    source_id: str
    source_url: Optional[str] = None
    collection_run_id: Optional[str] = None

    listing_type: Optional[str] = None
    property_type: Optional[str] = None
    title: Optional[str] = None
    price: Optional[str] = None
    area_sqm: Optional[str] = None
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None
    completion_status: Optional[str] = None
    payment_method: Optional[str] = None
    furnished: Optional[str] = None
    location_text: Optional[str] = None
    compound: Optional[str] = None
    description_full: Optional[str] = None
    posted_at: Optional[str] = None
    updated_at: Optional[str] = None
    scraped_at: Optional[str] = None
