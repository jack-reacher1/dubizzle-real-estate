from fastapi.testclient import TestClient
from app import app
from services.search import parse_smart_query

client = TestClient(app)

QUERIES = [
    "شقة 3 غرف أقل من 10 مليون",
    "شقة في Mountain View",
    "إيجار شقة غرفتين",
    "3 bedroom apartment under 10 million",
    "apartment in Mountain View",
]


def _ad_ids_from_response(resp):
    return [r.get("ad_id") for r in resp.get("results", [])]


def test_smart_search_e2e_parsed_vs_q():
    for q in QUERIES:
        parsed = parse_smart_query(q)
        # call via 'q' param
        r_q = client.get("/api/listings", params={"q": q})
        assert r_q.status_code == 200
        data_q = r_q.json()
        # call via parsed structured params
        params = {k: str(v) for k, v in parsed.items()}
        r_parsed = client.get("/api/listings", params=params)
        assert r_parsed.status_code == 200
        data_parsed = r_parsed.json()
        # The sets of ad_ids returned should be identical
        ids_q = _ad_ids_from_response(data_q)
        ids_parsed = _ad_ids_from_response(data_parsed)
        assert ids_q == ids_parsed, f"Mismatch for query '{q}': q_ids={ids_q} parsed_ids={ids_parsed}"
