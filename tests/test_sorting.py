from fastapi.testclient import TestClient
import importlib
app_module = importlib.import_module('app')
app = app_module.app
client = TestClient(app)
import csv


def write_business_rows(csv_path, rows):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['ad_id','ad_url','listing_type','title','price','area_sqm','bedrooms','bathrooms','property_type','completion_status','payment_method','furnished','location_text','compound','description_full','posted_at','updated_at','days_since_updated','seller_name','active_ads_count','likely_owner']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def reload_service(csv_path):
    # reload data into the running service instance
    app_module.service.csv_path = csv_path
    app_module.service._load()


def test_sort_newest_oldest_and_price_area(tmp_path):
    business_csv = tmp_path / 'data' / 'business_listings.csv'
    rows = [
        {'ad_id':'s1','ad_url':'u1','listing_type':'sale','title':'one','price':'300','area_sqm':'90','bedrooms':'2','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d1','posted_at':'2026-08-10','updated_at':'2026-08-13T12:00:00+00:00','days_since_updated':'1','seller_name':'A','active_ads_count':'1','likely_owner':'True'},
        {'ad_id':'s2','ad_url':'u2','listing_type':'sale','title':'two','price':'100','area_sqm':'120','bedrooms':'3','bathrooms':'2','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d2','posted_at':'2026-08-01','updated_at':'2026-08-12T11:00:00+00:00','days_since_updated':'10','seller_name':'B','active_ads_count':'1','likely_owner':'True'},
        {'ad_id':'s3','ad_url':'u3','listing_type':'sale','title':'three','price':'200','area_sqm':'80','bedrooms':'1','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d3','posted_at':'2026-07-01','updated_at':'2026-07-01T09:00:00+00:00','days_since_updated':'30','seller_name':'C','active_ads_count':'1','likely_owner':'True'},
    ]
    write_business_rows(business_csv, rows)
    reload_service(business_csv)

    # newest (by updated_at desc): expect s1 (2026-08-13), s2 (2026-08-12), s3 (2026-07-01)
    r = client.get('/api/listings?sort=newest')
    assert r.status_code == 200
    ids = [x['ad_id'] for x in r.json().get('results', [])]
    assert ids == ['s1','s2','s3']

    # oldest -> by updated_at asc -> s3, s2, s1
    r = client.get('/api/listings?sort=oldest')
    assert r.status_code == 200
    ids = [x['ad_id'] for x in r.json().get('results', [])]
    assert ids == ['s3','s2','s1']

    # price ascending -> s2(100), s3(200), s1(300)
    r = client.get('/api/listings?sort=price_asc')
    assert r.status_code == 200
    ids = [x['ad_id'] for x in r.json().get('results', [])]
    assert ids == ['s2','s3','s1']

    # price descending -> s1,s3,s2
    r = client.get('/api/listings?sort=price_desc')
    assert r.status_code == 200
    ids = [x['ad_id'] for x in r.json().get('results', [])]
    assert ids == ['s1','s3','s2']

    # area ascending -> s3(80), s1(90), s2(120)
    r = client.get('/api/listings?sort=area_asc')
    assert r.status_code == 200
    ids = [x['ad_id'] for x in r.json().get('results', [])]
    assert ids == ['s3','s1','s2']

    # area descending -> s2,s1,s3
    r = client.get('/api/listings?sort=area_desc')
    assert r.status_code == 200
    ids = [x['ad_id'] for x in r.json().get('results', [])]
    assert ids == ['s2','s1','s3']


def test_same_day_updated_timestamp_ordering(tmp_path):
    # two listings updated same day but different times - ensure ordering by updated_at
    business_csv = tmp_path / 'data' / 'business_listings.csv'
    rows = [
        {'ad_id':'t1','ad_url':'u1','listing_type':'sale','title':'t1','price':'100','area_sqm':'50','bedrooms':'1','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d','posted_at':'2026-08-14','updated_at':'2026-08-14T18:00:00+00:00','days_since_updated':'0','seller_name':'A','active_ads_count':'1','likely_owner':'True'},
        {'ad_id':'t2','ad_url':'u2','listing_type':'sale','title':'t2','price':'200','area_sqm':'60','bedrooms':'2','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d','posted_at':'2026-08-14','updated_at':'2026-08-14T12:00:00+00:00','days_since_updated':'0','seller_name':'B','active_ads_count':'1','likely_owner':'True'},
    ]
    write_business_rows(business_csv, rows)
    reload_service(business_csv)

    # newest should place t1 before t2 because 18:00 > 12:00
    r = client.get('/api/listings?sort=newest')
    assert r.status_code == 200
    ids = [x['ad_id'] for x in r.json().get('results', [])]
    assert ids[0:2] == ['t1','t2']
