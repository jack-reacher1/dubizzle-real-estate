import json
from pathlib import Path
from scraper import normalize_hit, build_ad_url, load_compound_choices


def test_window_state_compound_master_and_detection():
    path = Path('window_state.json')
    assert path.exists()
    # ensure the window_state contains a master 'compound' choices list
    choices = load_compound_choices(path)
    assert isinstance(choices, list) and len(choices) > 0

    data = json.loads(path.read_text(encoding='utf-8'))
    content = data.get('algolia', {}).get('content', {})
    hits = content.get('hits', [])
    # ensure at least one hit can be detected with a compound by matching text
    detected = 0
    sample_hit = None
    for h in hits:
        listing = normalize_hit(h, 'sale')
        if listing and getattr(listing, 'compound', None):
            detected += 1
            sample_hit = h
            break
    assert detected > 0, 'No compound could be detected by matching known choices in hit text'


def test_build_ad_url_pattern_and_live_check():
    path = Path('window_state.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    content = data.get('algolia', {}).get('content', {})
    hits = content.get('hits', [])
    h = None
    for hit in hits:
        if hit.get('slug') and (hit.get('id') or hit.get('objectID')):
            h = hit
            break
    assert h is not None
    # The live search payload does not include a canonical Dubizzle ad URL; it only
    # exposes a slug and other listing metadata. We deliberately do not fabricate a
    # URL from title+ID when no authoritative source URL is present.
    url = build_ad_url(h)
    assert url is None, 'The scraper must not invent a fake Dubizzle URL when the source payload does not provide one.'
