import pytest

from scraper import normalize_hit


@pytest.mark.parametrize("listing_type", ["sale", "rent"])
@pytest.mark.parametrize(
    "vacation_fields",
    [
        {"category": "عقارات مصايف للبيع"},
        {"property_type": "عقارات مصايف للايجار"},
        {"title": "Chalet for vacation"},
    ],
)
def test_normalize_hit_excludes_vacation_properties(listing_type, vacation_fields):
    hit = {
        "id": f"vacation-{listing_type}",
        "state": "active",
        "title": "Apartment in 5th Settlement",
        **vacation_fields,
    }

    assert normalize_hit(hit, listing_type) is None


@pytest.mark.parametrize("listing_type", ["sale", "rent"])
def test_normalize_hit_keeps_regular_properties(listing_type):
    hit = {
        "id": f"regular-{listing_type}",
        "state": "active",
        "title": "Apartment in 5th Settlement",
        "property_type": "Apartment",
    }

    listing = normalize_hit(hit, listing_type)

    assert listing is not None
    assert listing.listing_type == listing_type