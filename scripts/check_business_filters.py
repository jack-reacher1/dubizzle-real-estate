import csv
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / 'data'
LISTINGS = DATA / 'listings.csv'
SELLERS = DATA / 'sellers_cache.csv'
BUSINESS = DATA / 'business_listings.csv'
FRESHNESS_DAYS = 14
OWNER_RECHECK_DAYS = 30


def load_sellers():
    sellers = {}
    if not SELLERS.exists():
        return sellers
    with SELLERS.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            seller_id = row.get('seller_id')
            if seller_id:
                sellers[seller_id] = row
    return sellers


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


print('Data files:')
print(f' listings.csv: {LISTINGS.exists()}')
print(f' sellers_cache.csv: {SELLERS.exists()}')
print(f' business_listings.csv: {BUSINESS.exists()}')

if not LISTINGS.exists():
    raise SystemExit('listings.csv not found')

sellers = load_sellers()

counts = {
    'total_rows': 0,
    'active': 0,
    'not_agency': 0,
    'fresh': 0,
    'has_seller_id': 0,
    'seller_known': 0,
    'not_blacklisted': 0,
    'trusted_recently': 0,
    'classification_owner': 0,
    'passed_all': 0,
}

with LISTINGS.open(newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        counts['total_rows'] += 1
        if row.get('is_active', 'False') not in ('True', 'true', '1'):
            continue
        counts['active'] += 1

        if row.get('is_agency', 'False') in ('True', 'true', '1'):
            continue
        counts['not_agency'] += 1

        days = row.get('days_since_updated')
        if days is not None:
            try:
                if int(days) > FRESHNESS_DAYS:
                    continue
            except ValueError:
                pass
        counts['fresh'] += 1

        seller_id = row.get('seller_id')
        if not seller_id:
            continue
        counts['has_seller_id'] += 1

        seller = sellers.get(seller_id)
        if not seller:
            continue
        counts['seller_known'] += 1

        if seller.get('blocklist_permanent') == 'True':
            continue
        counts['not_blacklisted'] += 1

        checked_at = seller.get('checked_at')
        trusted = False
        if checked_at:
            checked_dt = parse_iso(checked_at)
            if checked_dt is not None:
                age_days = (datetime.now(timezone.utc) - checked_dt).days
                if age_days <= OWNER_RECHECK_DAYS:
                    trusted = True
        if not trusted:
            continue
        counts['trusted_recently'] += 1

        if seller.get('classification') != 'owner':
            continue
        counts['classification_owner'] += 1

        counts['passed_all'] += 1

print('\nFilter counts using exact business logic from scraper.py:')
for k,v in counts.items():
    print(f'  {k}: {v}')

if BUSINESS.exists():
    with BUSINESS.open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    print(f'\nCurrent business_listings.csv rows: {len(rows)}')
else:
    print('\nCurrent business_listings.csv missing')
