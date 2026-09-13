import csv

from scraper import Listing, build_ad_url, generate_business_dataset, merge_and_save, normalize_hit


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


def test_generate_business_dataset(tmp_path):
    data_dir = tmp_path / 'data'
    listings = [
        {'ad_id':'1','ad_url':'u','listing_type':'sale','title':'t','price':'100','area_sqm':'100','bedrooms':'2','bathrooms':'1','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C1','description_full':'d','posted_at':'2026-08-01','days_since_updated':'1','seller_id':'s1','seller_name':'Ahmed','is_active':'True','is_agency':'False'},
        {'ad_id':'2','ad_url':'u2','listing_type':'sale','title':'t2','price':'200','area_sqm':'120','bedrooms':'3','bathrooms':'2','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C2','description_full':'d2','posted_at':'2026-07-01','days_since_updated':'40','seller_id':'s2','seller_name':'Agency','is_active':'True','is_agency':'True'},
        {'ad_id':'3','ad_url':'u3','listing_type':'sale','title':'t3','price':'300','area_sqm':'130','bedrooms':'3','bathrooms':'2','property_type':'Apartment','completion_status':'Ready','payment_method':'Cash','furnished':'No','location_text':'LT','compound':'C3','description_full':'d3','posted_at':'2026-06-01','days_since_updated':'50','seller_id':'s3','seller_name':'Ali','is_active':'False','is_agency':'False'},
    ]
    sellers = [
        {'seller_id':'s1','seller_name':'Ahmed','active_ads_count':'1','classification':'owner','checked_at':'2026-08-01T00:00:00+00:00','blocklist_permanent':'False'},
        {'seller_id':'s2','seller_name':'Agency','active_ads_count':'10','classification':'broker','checked_at':'2026-08-01T00:00:00+00:00','blocklist_permanent':'True'},
    ]
    listings_csv, sellers_csv = _write_fixture(data_dir, listings, sellers)

    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=listings_csv, sellers_csv=sellers_csv, out_csv=out)
    assert out.exists()
    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]['ad_id'] == '1'
    assert rows[0]['likely_owner'] == 'True'


def test_merge_and_save_prunes_inactive_rows(tmp_path):
    data_dir = tmp_path / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    listings_csv = data_dir / 'listings.csv'

    with open(listings_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=['ad_id','ad_url','listing_type','title','price','area_sqm','bedrooms','bathrooms','property_type','completion_status','payment_method','ownership','furnished','location_text','compound','location_link','amenities','description_full','phone_in_description','posted_at','updated_at','scraped_at','days_since_updated','is_verified_business','is_agency','agency_name','has_broker_code_pattern','seller_repeat_count','seller_id','seller_name','first_seen_date','last_seen_date','is_active'],
        )
        writer.writeheader()
        writer.writerow({
            'ad_id': 'old-inactive',
            'ad_url': 'https://example.com/old',
            'listing_type': 'sale',
            'title': 'old',
            'price': '100',
            'area_sqm': '80',
            'bedrooms': '2',
            'bathrooms': '2',
            'property_type': 'Apartment',
            'completion_status': 'Ready',
            'payment_method': 'Cash',
            'ownership': 'Freehold',
            'furnished': 'No',
            'location_text': 'New Cairo',
            'compound': 'The Fifth',
            'location_link': '',
            'amenities': '',
            'description_full': 'old',
            'phone_in_description': '',
            'posted_at': '2026-08-10',
            'updated_at': '2026-08-10T00:00:00+00:00',
            'scraped_at': '2026-08-10T00:00:00+00:00',
            'days_since_updated': '0',
            'is_verified_business': 'False',
            'is_agency': 'False',
            'agency_name': '',
            'has_broker_code_pattern': 'False',
            'seller_repeat_count': '0',
            'seller_id': 's_old',
            'seller_name': 'Old Seller',
            'first_seen_date': '2026-08-01',
            'last_seen_date': '2026-07-01',
            'is_active': 'False',
        })
        writer.writerow({
            'ad_id': 'recent-inactive',
            'ad_url': 'https://example.com/recent',
            'listing_type': 'sale',
            'title': 'recent',
            'price': '120',
            'area_sqm': '85',
            'bedrooms': '2',
            'bathrooms': '2',
            'property_type': 'Apartment',
            'completion_status': 'Ready',
            'payment_method': 'Cash',
            'ownership': 'Freehold',
            'furnished': 'No',
            'location_text': 'New Cairo',
            'compound': 'The Fifth',
            'location_link': '',
            'amenities': '',
            'description_full': 'recent',
            'phone_in_description': '',
            'posted_at': '2026-08-20',
            'updated_at': '2026-08-20T00:00:00+00:00',
            'scraped_at': '2026-08-20T00:00:00+00:00',
            'days_since_updated': '0',
            'is_verified_business': 'False',
            'is_agency': 'False',
            'agency_name': '',
            'has_broker_code_pattern': 'False',
            'seller_repeat_count': '0',
            'seller_id': 's_recent',
            'seller_name': 'Recent Seller',
            'first_seen_date': '2026-08-18',
            'last_seen_date': '2026-08-20',
            'is_active': 'False',
        })

    merge_and_save([
        Listing(
            ad_id='new-active',
            ad_url='https://example.com/new',
            listing_type='sale',
            title='new',
            price='250',
            area_sqm='100',
            bedrooms='3',
            bathrooms='2',
            completion_status='Ready',
            payment_method='Cash',
            ownership='Freehold',
            furnished='No',
            location_text='New Cairo',
            compound='The Fifth',
            description_full='new',
            posted_at='2026-08-21',
            updated_at='2026-08-21T00:00:00+00:00',
            scraped_at='2026-08-21T00:00:00+00:00',
            days_since_updated='0',
            is_verified_business='False',
            is_agency='False',
            agency_name='',
            has_broker_code_pattern='False',
            seller_repeat_count='0',
            seller_id='s_new',
            seller_name='New Seller',
            first_seen_date='2026-08-21',
            last_seen_date='2026-08-21',
            is_active=True,
        )
    ])

    with open(listings_csv, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    assert {row['ad_id'] for row in rows} == {'new-active', 'recent-inactive'}


def test_build_ad_url_prefers_canonical_source_url():
    hit = {
        'id': '28407570',
        'slug': 'fake-title',
        'title': 'A fake title',
        'canonical_url': 'https://www.dubizzle.com.eg/en/ad/real-canonical-title-ID28407570.html',
        'external_link': 'https://www.bayut.eg/for-sale/example.html',
    }
    assert build_ad_url(hit) == 'https://www.dubizzle.com.eg/en/ad/real-canonical-title-ID28407570.html'


def test_build_ad_url_rejects_faux_generated_url_when_no_source_url_exists():
    hit = {
        'id': '28407570',
        'slug': 'a-fake-classic-title',
        'title': 'A fake title',
        'objectID': '28407570',
    }
    assert build_ad_url(hit) is None
    normalized = normalize_hit(hit, 'sale')
    assert normalized is not None
    assert normalized.ad_url is None


def test_business_dataset_preserves_canonical_ad_url(tmp_path):
    data_dir = tmp_path / 'data'
    listings = [
        {
            'ad_id': '10',
            'ad_url': 'https://www.dubizzle.com.eg/en/ad/real-canonical-title-ID10.html',
            'listing_type': 'sale',
            'title': 'real canonical title',
            'price': '100',
            'area_sqm': '100',
            'bedrooms': '2',
            'bathrooms': '1',
            'property_type': 'Apartment',
            'completion_status': 'Ready',
            'payment_method': 'Cash',
            'furnished': 'No',
            'location_text': 'LT',
            'compound': 'C1',
            'description_full': 'd',
            'posted_at': '2026-08-01',
            'days_since_updated': '1',
            'seller_id': 's1',
            'seller_name': 'Ahmed',
            'is_active': 'True',
            'is_agency': 'False',
        }
    ]
    sellers = [
        {'seller_id': 's1', 'seller_name': 'Ahmed', 'active_ads_count': '1', 'classification': 'owner', 'checked_at': '2026-08-01T00:00:00+00:00', 'blocklist_permanent': 'False'},
    ]
    listings_csv = data_dir / 'listings.csv'
    sellers_csv = data_dir / 'sellers_cache.csv'
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(listings_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['ad_id','ad_url','listing_type','title','price','area_sqm','bedrooms','bathrooms','property_type','completion_status','payment_method','furnished','location_text','compound','description_full','posted_at','days_since_updated','seller_id','seller_name','is_active','is_agency'])
        writer.writeheader()
        writer.writerow(listings[0])
    with open(sellers_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['seller_id','seller_name','active_ads_count','classification','checked_at','blocklist_permanent'])
        writer.writeheader()
        writer.writerow(sellers[0])

    out = data_dir / 'business_listings.csv'
    generate_business_dataset(listings_csv=listings_csv, sellers_csv=sellers_csv, out_csv=out)
    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert rows[0]['ad_url'] == 'https://www.dubizzle.com.eg/en/ad/real-canonical-title-ID10.html'
