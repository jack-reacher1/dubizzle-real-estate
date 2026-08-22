import re

# Basic rule-based parser for Smart Search (Phase 1)
# Returns dict of filters compatible with ListingsService.query

MILLION_RE = re.compile(r"(\d+[\.,]?\d*)\s*(?:مليون|million)", re.I)
THOUSAND_RE = re.compile(r"(\d+[\.,]?\d*)\s*(?:ألف|thousand|k)\b", re.I)
BEDROOMS_AR = re.compile(r"(\d+)\s*غرف")
BEDROOMS_EN = re.compile(r"(\d+)\s*(?:rooms|bed|beds)", re.I)
PRICE_LESS_AR = re.compile(r"أقل من\s*(\d+[\.,]?\d*)\s*(مليون|ألف)?")
PRICE_LESS_EN = re.compile(r"less than\s*(\d+[\.,]?\d*)\s*(million|k|thousand)?", re.I)
COMP_IN = re.compile(r"في\s+([A-Za-z0-9\-\s]+)")
COMP_IN_EN = re.compile(r"in\s+([A-Za-z0-9\-\s]+)", re.I)
PROPERTY_AR = [(re.compile(r"شقة"), "Apartment"), (re.compile(r"فيلا"), "Villa")]
PROPERTY_EN = [(re.compile(r"apartment", re.I), "Apartment"), (re.compile(r"villa", re.I), "Villa")]


def parse_smart_query(q: str) -> dict:
    q = q.strip()
    out = {}
    if not q:
        return out
    # sale/rent
    if re.search(r"للبيع|بيع|sale", q):
        out["listing_type"] = "sale"
    if re.search(r"للإيجار|إيجار|rent", q):
        out["listing_type"] = "rent"

    # property type
    for pat, val in PROPERTY_AR + PROPERTY_EN:
        if pat.search(q):
            out["property_type"] = val
            break

    # bedrooms
    m = BEDROOMS_AR.search(q) or BEDROOMS_EN.search(q)
    if m:
        try:
            out["bedrooms_min"] = int(m.group(1))
        except Exception:
            pass

    # price less than
    m = PRICE_LESS_AR.search(q)
    if m:
        num = float(m.group(1).replace(',', '.'))
        unit = m.group(2)
        if unit and 'مليون' in unit:
            out["max_price"] = int(num * 1_000_000)
        elif unit and 'ألف' in unit:
            out["max_price"] = int(num * 1_000)
        else:
            out["max_price"] = int(num)
    else:
        m = PRICE_LESS_EN.search(q)
        if m:
            num = float(m.group(1).replace(',', '.'))
            unit = m.group(2) or ''
            if 'million' in unit.lower():
                out["max_price"] = int(num * 1_000_000)
            elif unit.lower() in ('k', 'thousand'):
                out["max_price"] = int(num * 1_000)
            else:
                out["max_price"] = int(num)

    # compound
    m = COMP_IN.search(q)
    if not m:
        m = COMP_IN_EN.search(q)
    if m:
        candidate = m.group(1).strip()
        # strip trailing words that are not part of compound (basic)
        candidate = re.sub(r"\s+(أقل|less|مليون|million|غرف|rooms|بالقرب).*", "", candidate)
        out["compound"] = candidate

    return out
