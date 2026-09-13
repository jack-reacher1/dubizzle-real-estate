import csv

from scraper import generate_business_dataset


def _write_fixture(data_dir, listings, sellers):
    data_dir.mkdir(parents=True, exist_ok=True)
    listings_csv = data_dir / 'listings.csv'
    sellers_csv = data_dir / 'sellers_cache.csv'

    with open(listings_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=['ad_id','ad_url','listing_type','title','price','area_sqm','bedrooms','bathrooms','property_type','completion_status','payment_method','furnished','location_text','compound','description_full','posted_at','days_since_updated','seller_id','seller_name','is_active','is_agency'],
        )
        writer.writeheader()
        for r in listings:
            writer.writerow(r)

    with open(sellers_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=['seller_id','seller_name','active_ads_count','active_ads_count_source','classification','checked_at','blocklist_permanent'],
        )
        writer.writeheader()
        for s in sellers:
            writer.writerow(s)

    return listings_csv, sellers_csv


def _owner(seller_id, seller_name='Owner', count='1', checked='2099-01-01T00:00:00+00:00'):
    return {'seller_id': seller_id, 'seller_name': seller_name, 'active_ads_count': count,
            'active_ads_count_source': 'seller_profile', 'classification': 'owner',
            'checked_at': checked, 'blocklist_permanent': 'False'}


def _listing(ad_id, seller_id, days='1', agency='False', active='True'):
    return {'ad_id': ad_id, 'ad_url': '', 'listing_type': 'sale', 'title': 't', 'price': '100',
            'area_sqm': '100', 'bedrooms': '2', 'bathrooms': '1', 'property_type': 'Apartment',
            'completion_status': 'Ready', 'payment_method': 'Cash', 'furnished': 'No',
            'location_text': 'LT', 'compound': 'C1', 'description_full': 'd',
            'posted_at': '2026-08-01', 'days_since_updated': days, 'seller_id': seller_id,
            'seller_name': seller_id, 'is_active': active, 'is_agency': agency}


def _read_business(out):
    with open(out, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def test_broker_with_blocklist_flag_excluded(tmp_path):
    # Classification = broker AND blocklist_permanent = True -> excluded.
    listings = [_listing('L1', 's_broker_block'), _listing('L2', 's_ok')]
    sellers = [
        {'seller_id': 's_broker_block', 'seller_name': 'Broker', 'active_ads_count': '10',
         'active_ads_count_source': 'seller_profile', 'classification': 'broker',
         'checked_at': '2099-01-01T00:00:00+00:00', 'blocklist_permanent': 'True'},
        _owner('s_ok'),
    ]
    data_dir = tmp_path / 'data'
    listings_csv, sellers_csv = _write_fixture(data_dir, listings, sellers)
    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=listings_csv, sellers_csv=sellers_csv, out_csv=out)
    rows = _read_business(out)
    assert rows[0]['ad_id'] == 'L2'
    assert all(r['ad_id'] != 'L1' for r in rows)


def test_broker_without_blocklist_flag_still_excluded(tmp_path):
    # A seller classified broker must be excluded from the business dataset
    # even if the blocklist flag was never set - classification is the rule.
    listings = [_listing('L1', 's_broker'), _listing('L2', 's_ok')]
    sellers = [
        {'seller_id': 's_broker', 'seller_name': 'Broker', 'active_ads_count': '8',
         'active_ads_count_source': 'seller_profile', 'classification': 'broker',
         'checked_at': '2099-01-01T00:00:00+00:00', 'blocklist_permanent': 'False'},
        _owner('s_ok'),
    ]
    data_dir = tmp_path / 'data'
    listings_csv, sellers_csv = _write_fixture(data_dir, listings, sellers)
    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=listings_csv, sellers_csv=sellers_csv, out_csv=out)
    rows = _read_business(out)
    assert all(r['ad_id'] != 'L1' for r in rows)
    assert rows[0]['ad_id'] == 'L2'


def test_unclassified_seller_excluded(tmp_path):
    # No classification -> must NOT be treated as owner (inference needs trust).
    listings = [_listing('L1', 's_unknown')]
    sellers = [
        {'seller_id': 's_unknown', 'seller_name': 'Unknown', 'active_ads_count': '',
         'active_ads_count_source': 'unknown', 'classification': '',
         'checked_at': '2099-01-01T00:00:00+00:00', 'blocklist_permanent': 'False'},
    ]
    data_dir = tmp_path / 'data'
    listings_csv, sellers_csv = _write_fixture(data_dir, listings, sellers)
    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=listings_csv, sellers_csv=sellers_csv, out_csv=out)
    rows = _read_business(out)
    assert len(rows) == 0
