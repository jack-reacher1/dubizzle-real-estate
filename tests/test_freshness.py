from fastapi.testclient import TestClient
import importlib
app_module = importlib.import_module('app')
app = app_module.app
client = TestClient(app)
import csv


def write(csv_path, rows):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames=['ad_id','ad_url','listing_type','title','price','area_sqm','bedrooms','bathrooms','property_type','completion_status','payment_method','furnished','location_text','compound','description_full','posted_at','days_since_updated','seller_name','active_ads_count','likely_owner']
    with open(csv_path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def reload(csv_path):
    app_module.service.csv_path = csv_path
    app_module.service._load()


def test_freshness_filters(tmp_path):
    business_csv = tmp_path / 'data' / 'business_listings.csv'
    # create rows with days_since_updated 0,2,5,10,20
    rows=[
        {'ad_id':'d0','ad_url':'u','listing_type':'sale','title':'d0','price':'100','area_sqm':'50','bedrooms':'1','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d','posted_at':'2026-08-14','days_since_updated':'0','seller_name':'A','active_ads_count':'1','likely_owner':'True'},
        {'ad_id':'d2','ad_url':'u','listing_type':'sale','title':'d2','price':'100','area_sqm':'50','bedrooms':'1','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d','posted_at':'2026-08-12','days_since_updated':'2','seller_name':'A','active_ads_count':'1','likely_owner':'True'},
        {'ad_id':'d5','ad_url':'u','listing_type':'sale','title':'d5','price':'100','area_sqm':'50','bedrooms':'1','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d','posted_at':'2026-08-09','days_since_updated':'5','seller_name':'A','active_ads_count':'1','likely_owner':'True'},
        {'ad_id':'d10','ad_url':'u','listing_type':'sale','title':'d10','price':'100','area_sqm':'50','bedrooms':'1','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d','posted_at':'2026-08-04','days_since_updated':'10','seller_name':'A','active_ads_count':'1','likely_owner':'True'},
        {'ad_id':'d20','ad_url':'u','listing_type':'sale','title':'d20','price':'100','area_sqm':'50','bedrooms':'1','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d','posted_at':'2026-07-25','days_since_updated':'20','seller_name':'A','active_ads_count':'1','likely_owner':'True'},
    ]
    write(business_csv, rows)
    reload(business_csv)

    # freshness=1 -> last 24 hours -> only d0
    r = client.get('/api/listings?freshness=1')
    assert r.status_code == 200
    ids=[x['ad_id'] for x in r.json().get('results',[])]
    assert ids == ['d0']

    # freshness=3 -> d0,d2
    r = client.get('/api/listings?freshness=3')
    ids=[x['ad_id'] for x in r.json().get('results',[])]
    assert ids == ['d0','d2']

    # freshness=7 -> d0,d2,d5
    r = client.get('/api/listings?freshness=7')
    ids=[x['ad_id'] for x in r.json().get('results',[])]
    assert ids == ['d0','d2','d5']

    # freshness=14 -> d0,d2,d5,d10
    r = client.get('/api/listings?freshness=14')
    ids=[x['ad_id'] for x in r.json().get('results',[])]
    assert ids == ['d0','d2','d5','d10']

    # freshness large -> all
    r = client.get('/api/listings?freshness=30')
    ids=[x['ad_id'] for x in r.json().get('results',[])]
    assert set(ids) == set(['d0','d2','d5','d10','d20'])
