from sources.base import SourceCollector, SourceParser, SourceNormalizer
from domain.normalized_listing import NormalizedListing
from domain.raw_event import RawSourceEvent


def test_normalized_listing_contract_supports_source_identity_and_common_fields():
    item = NormalizedListing(
        source="dubizzle",
        source_id="ad-123",
        source_url="https://example.test/ad/123",
        collection_run_id="run-abc",
        listing_type="sale",
        property_type="Apartment",
        title="Apartment in Fifth Settlement",
        price="2500000",
        area_sqm="90",
        bedrooms="2",
        bathrooms="1",
        location_text="Fifth Settlement",
        compound="Madinty",
        description_full="Owner listing",
        posted_at="2026-09-14",
        updated_at="2026-09-14",
    )

    assert item.source == "dubizzle"
    assert item.source_id == "ad-123"
    assert item.source_url == "https://example.test/ad/123"
    assert item.collection_run_id == "run-abc"
    assert item.listing_type == "sale"
    assert item.property_type == "Apartment"
    assert item.location_text == "Fifth Settlement"


def test_raw_source_event_contract_captures_source_identity_and_payload():
    event = RawSourceEvent(
        source="dubizzle",
        source_id="ad-123",
        source_url="https://example.test/ad/123",
        raw_payload={"title": "Apartment in Fifth Settlement"},
        collected_at="2026-09-14T00:00:00+00:00",
        collection_run_id="run-abc",
    )

    assert event.source == "dubizzle"
    assert event.source_id == "ad-123"
    assert event.source_url == "https://example.test/ad/123"
    assert event.raw_payload["title"] == "Apartment in Fifth Settlement"
    assert event.collection_run_id == "run-abc"


def test_source_boundary_contracts_are_defined_as_shared_interfaces():
    assert hasattr(SourceCollector, "collect")
    assert hasattr(SourceParser, "parse")
    assert hasattr(SourceNormalizer, "normalize")
