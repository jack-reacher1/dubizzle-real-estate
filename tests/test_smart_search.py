from services.search import parse_smart_query


def test_smart_search_arabic_example():
    q = "شقة 3 غرف في Mountain View أقل من 10 مليون"
    parsed = parse_smart_query(q)
    assert parsed.get('property_type') == 'Apartment'
    assert parsed.get('bedrooms_min') == 3
    assert parsed.get('compound') and 'Mountain' in parsed.get('compound')
    assert parsed.get('max_price') == 10000000


def test_smart_search_english():
    q = "Apartment 2 beds in Hyde Park less than 500k"
    parsed = parse_smart_query(q)
    assert parsed.get('property_type') == 'Apartment'
    assert parsed.get('bedrooms_min') == 2
    assert parsed.get('compound') and 'Hyde' in parsed.get('compound')
    assert parsed.get('max_price') == 500000
