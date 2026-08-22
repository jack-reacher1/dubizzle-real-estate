import csv
from pathlib import Path

from scraper import migrate_sellers_cache


def _write_cache(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['seller_id','seller_name','active_ads_count','active_ads_count_source','classification','checked_at','blocklist_permanent'])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def test_migration_clears_unproven_zero(tmp_path):
    sc = tmp_path / 'data' / 'sellers_cache.csv'
    rows = [
        {'seller_id':'a','seller_name':'A','active_ads_count':'0','active_ads_count_source':'','classification':'owner','checked_at':'2025-01-01T00:00:00+00:00','blocklist_permanent':'False'},
        {'seller_id':'b','seller_name':'B','active_ads_count':'5','active_ads_count_source':'seller_profile','classification':'owner','checked_at':'2026-01-01T00:00:00+00:00','blocklist_permanent':'False'},
        {'seller_id':'c','seller_name':'C','active_ads_count':'0','active_ads_count_source':'seller_profile','classification':'owner','checked_at':'2026-01-01T00:00:00+00:00','blocklist_permanent':'False'},
    ]
    _write_cache(sc, rows)
    summary = migrate_sellers_cache(sc)
    assert summary['total'] == 3
    assert summary['zeros_before'] == 2
    assert summary['zeros_migrated'] == 1  # only the unproven zero should be migrated

    # re-open and assert
    with open(sc, encoding='utf-8') as f:
        data = list(csv.DictReader(f))
    # seller a should have been cleared
    a = [r for r in data if r['seller_id']=='a'][0]
    assert a['active_ads_count'] == ''
    assert a['active_ads_count_source'] == 'unknown'
    # seller b unaffected
    b = [r for r in data if r['seller_id']=='b'][0]
    assert b['active_ads_count'] == '5'
    assert b['active_ads_count_source'] == 'seller_profile'
    # seller c was explicit 0 with provenance -> keep
    c = [r for r in data if r['seller_id']=='c'][0]
    assert c['active_ads_count'] == '0'
    assert c['active_ads_count_source'] == 'seller_profile'
