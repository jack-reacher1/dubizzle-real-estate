import csv

from scraper import generate_business_dataset


def write_fixture(data_dir, listings, sellers):
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
            fieldnames=['seller_id','seller_name','active_ads_count','classification','checked_at','blocklist_permanent'],
        )
        writer.writeheader()
        for s in sellers:
            writer.writerow(s)

    return listings_csv, sellers_csv


def test_business_rules_exclusions_and_inclusions(tmp_path):
    listings = [
        # eligible owner
        {'ad_id':'A1','ad_url':'u','listing_type':'sale','title':'ok','price':'100','area_sqm':'100','bedrooms':'2','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C1','description_full':'d','posted_at':'2026-08-01','days_since_updated':'1','seller_id':'s_ok','seller_name':'Owner','is_active':'True','is_agency':'False'},
        # agency - excluded
        {'ad_id':'A2','ad_url':'u2','listing_type':'sale','title':'agency','price':'200','area_sqm':'120','bedrooms':'3','bathrooms':'2','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C2','description_full':'d2','posted_at':'2026-07-01','days_since_updated':'2','seller_id':'s_ag','seller_name':'Agency','is_active':'True','is_agency':'True'},
        # blacklisted seller - excluded
        {'ad_id':'A3','ad_url':'u3','listing_type':'sale','title':'blk','price':'300','area_sqm':'130','bedrooms':'3','bathrooms':'2','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C3','description_full':'d3','posted_at':'2026-06-01','days_since_updated':'1','seller_id':'s_blk','seller_name':'Bad','is_active':'True','is_agency':'False'},
        # inactive - excluded
        {'ad_id':'A4','ad_url':'u4','listing_type':'sale','title':'inactive','price':'400','area_sqm':'140','bedrooms':'4','bathrooms':'3','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C4','description_full':'d4','posted_at':'2026-05-01','days_since_updated':'1','seller_id':'s_in','seller_name':'Ina','is_active':'False','is_agency':'False'},
        # missing seller id - excluded
        {'ad_id':'A5','ad_url':'u5','listing_type':'sale','title':'noseller','price':'500','area_sqm':'150','bedrooms':'4','bathrooms':'3','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C5','description_full':'d5','posted_at':'2026-05-01','days_since_updated':'1','seller_id':'','seller_name':'','is_active':'True','is_agency':'False'},
        # stale listing (days_since_updated > 14) - excluded
        {'ad_id':'A6','ad_url':'u6','listing_type':'sale','title':'stale','price':'600','area_sqm':'160','bedrooms':'4','bathrooms':'3','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C6','description_full':'d6','posted_at':'2026-01-01','days_since_updated':'30','seller_id':'s_ok','seller_name':'Owner','is_active':'True','is_agency':'False'},
    ]
    sellers = [
        {'seller_id':'s_ok','seller_name':'Owner','active_ads_count':'1','classification':'owner','checked_at':'2026-08-01T00:00:00+00:00','blocklist_permanent':'False'},
        {'seller_id':'s_ag','seller_name':'Agency','active_ads_count':'10','classification':'broker','checked_at':'2026-08-01T00:00:00+00:00','blocklist_permanent':'True'},
        {'seller_id':'s_blk','seller_name':'Bad','active_ads_count':'5','classification':'broker','checked_at':'2026-08-01T00:00:00+00:00','blocklist_permanent':'True'},
        {'seller_id':'s_in','seller_name':'Ina','active_ads_count':'0','classification':'owner','checked_at':'2026-08-01T00:00:00+00:00','blocklist_permanent':'False'},
    ]
    data_dir = tmp_path / 'data'
    listings_csv, sellers_csv = write_fixture(data_dir, listings, sellers)
    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=listings_csv, sellers_csv=sellers_csv, out_csv=out)
    assert out.exists()
    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]['ad_id'] == 'A1'
    assert 'is_active' not in rows[0]
    assert 'seller_id' not in rows[0]
    assert rows[0]['active_ads_count'] == '1'
