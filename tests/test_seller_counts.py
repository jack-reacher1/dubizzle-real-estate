import csv
from pathlib import Path
from datetime import datetime, timezone

from scraper import generate_business_dataset


def _write_fixture(data_dir, listings, sellers):
    data_dir.mkdir(parents=True, exist_ok=True)
    listings_csv = data_dir / 'listings.csv'
    sellers_csv = data_dir / 'sellers_cache.csv'

    with open(listings_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                'ad_id','ad_url','listing_type','title','price','area_sqm','bedrooms','bathrooms',
                'property_type','completion_status','payment_method','furnished','location_text',
                'compound','description_full','posted_at','days_since_updated','seller_id','seller_name',
                'is_active','is_agency'
            ],
        )
        writer.writeheader()
        for row in listings:
            writer.writerow(row)

    with open(sellers_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=['seller_id','seller_name','active_ads_count','classification','checked_at','blocklist_permanent'],
        )
        writer.writeheader()
        for row in sellers:
            writer.writerow(row)

    return listings_csv, sellers_csv


def test_active_ads_count_zero_preserved(tmp_path):
    data_dir = tmp_path / 'data'
    listings = [
        {'ad_id':'1','ad_url':'u','listing_type':'sale','title':'t','price':'100','area_sqm':'100','bedrooms':'2','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C1','description_full':'d','posted_at':'2026-08-01','days_since_updated':'1','seller_id':'s1','seller_name':'Ahmed','is_active':'True','is_agency':'False'},
    ]
    sellers = [
        {'seller_id':'s1','seller_name':'Ahmed','active_ads_count':'0','classification':'owner','checked_at':'2026-08-01T00:00:00+00:00','blocklist_permanent':'False'},
    ]
    _write_fixture(data_dir, listings, sellers)

    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=data_dir / 'listings.csv', sellers_csv=data_dir / 'sellers_cache.csv', out_csv=out)
    assert out.exists()
    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]['active_ads_count'] == '0'


def test_active_ads_count_positive_preserved(tmp_path):
    data_dir = tmp_path / 'data'
    listings = [
        {'ad_id':'2','ad_url':'u2','listing_type':'sale','title':'t2','price':'200','area_sqm':'120','bedrooms':'3','bathrooms':'2','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C2','description_full':'d2','posted_at':'2026-08-01','days_since_updated':'1','seller_id':'s2','seller_name':'Hussein','is_active':'True','is_agency':'False'},
    ]
    sellers = [
        {'seller_id':'s2','seller_name':'Hussein','active_ads_count':'7','classification':'owner','checked_at':'2026-08-01T00:00:00+00:00','blocklist_permanent':'False'},
    ]
    _write_fixture(data_dir, listings, sellers)

    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=data_dir / 'listings.csv', sellers_csv=data_dir / 'sellers_cache.csv', out_csv=out)
    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert rows[0]['active_ads_count'] == '7'


def test_active_ads_count_null_results_in_empty_field(tmp_path):
    data_dir = tmp_path / 'data'
    listings = [
        {'ad_id':'3','ad_url':'u3','listing_type':'sale','title':'t3','price':'300','area_sqm':'130','bedrooms':'3','bathrooms':'2','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C3','description_full':'d3','posted_at':'2026-08-01','days_since_updated':'1','seller_id':'s3','seller_name':'Omar','is_active':'True','is_agency':'False'},
    ]
    # trusted classification exists but active_ads_count unknown (empty)
    sellers = [
        {'seller_id':'s3','seller_name':'Omar','active_ads_count':'','classification':'owner','checked_at':'2026-08-01T00:00:00+00:00','blocklist_permanent':'False'},
    ]
    _write_fixture(data_dir, listings, sellers)

    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=data_dir / 'listings.csv', sellers_csv=data_dir / 'sellers_cache.csv', out_csv=out)
    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert rows[0]['active_ads_count'] == ''


def test_live_profile_lookup_fails_and_no_cache_excludes_listing(tmp_path):
    data_dir = tmp_path / 'data'
    listings = [
        {'ad_id':'4','ad_url':'u4','listing_type':'sale','title':'t4','price':'400','area_sqm':'140','bedrooms':'4','bathrooms':'3','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C4','description_full':'d4','posted_at':'2026-08-01','days_since_updated':'1','seller_id':'s4','seller_name':'Mahmoud','is_active':'True','is_agency':'False'},
    ]
    sellers = []  # no trusted cache
    _write_fixture(data_dir, listings, sellers)

    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=data_dir / 'listings.csv', sellers_csv=data_dir / 'sellers_cache.csv', out_csv=out)
    # should be created but empty (only header)
    assert out.exists()
    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 0


def test_live_profile_lookup_fails_but_trusted_cache_keeps_classification(tmp_path):
    data_dir = tmp_path / 'data'
    listings = [
        {'ad_id':'5','ad_url':'u5','listing_type':'sale','title':'t5','price':'500','area_sqm':'150','bedrooms':'5','bathrooms':'4','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C5','description_full':'d5','posted_at':'2026-08-01','days_since_updated':'1','seller_id':'s5','seller_name':'Sayed','is_active':'True','is_agency':'False'},
    ]
    # cached classification exists but active_ads_count missing -> should include listing and keep empty count
    sellers = [
        {'seller_id':'s5','seller_name':'Sayed','active_ads_count':'','classification':'owner','checked_at': (datetime.now(timezone.utc).isoformat()), 'blocklist_permanent':'False'},
    ]
    _write_fixture(data_dir, listings, sellers)

    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=data_dir / 'listings.csv', sellers_csv=data_dir / 'sellers_cache.csv', out_csv=out)
    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]['active_ads_count'] == ''
