from fastapi.testclient import TestClient
import importlib
app_module = importlib.import_module('app')
app = app_module.app
client = TestClient(app)
import csv


def write_many(csv_path, n, per_page=5):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames=['ad_id','ad_url','listing_type','title','price','area_sqm','bedrooms','bathrooms','property_type','completion_status','payment_method','furnished','location_text','compound','description_full','posted_at','days_since_updated','seller_name','active_ads_count','likely_owner']
    rows=[]
    for i in range(n):
        rows.append({'ad_id':f'p{i}','ad_url':'u','listing_type':'sale','title':f't{i}','price':str(100+i),'area_sqm':'50','bedrooms':'1','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'L','compound':'C','description_full':'d','posted_at':'2026-08-01','days_since_updated':'1','seller_name':'A','active_ads_count':'1','likely_owner':'True'})
    with open(csv_path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return rows


def reload(csv_path):
    app_module.service.csv_path = csv_path
    app_module.service._load()


def test_pagination_pages_differ(tmp_path):
    business_csv = tmp_path / 'data' / 'business_listings.csv'
    rows=write_many(business_csv, 12)
    reload(business_csv)
    # small per_page to force multiple pages
    r1=client.get('/api/listings?per_page=5&page=1')
    r2=client.get('/api/listings?per_page=5&page=2')
    assert r1.status_code==200 and r2.status_code==200
    ids1=[x['ad_id'] for x in r1.json().get('results',[])]
    ids2=[x['ad_id'] for x in r2.json().get('results',[])]
    assert ids1 != ids2
    # ensure no duplicate IDs across pages
    assert set(ids1).isdisjoint(set(ids2))


def test_duplicate_page_safeguard(tmp_path):
    # if page beyond range, empty results expected but page number returned should match
    business_csv = tmp_path / 'data' / 'business_listings.csv'
    rows=write_many(business_csv, 3)
    reload(business_csv)
    r=client.get('/api/listings?per_page=2&page=10')
    assert r.status_code==200
    assert r.json().get('results',[])==[]
    assert r.json().get('page')==10
