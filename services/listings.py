import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

from services.search import parse_smart_query


DATA_DIR = Path("data")
BUSINESS_CSV = DATA_DIR / "business_listings.csv"


class ListingsService:
    def __init__(self, csv_path: Path = BUSINESS_CSV):
        self.csv_path = csv_path
        self._load()

    def _load(self):
        self.rows: List[Dict[str, Any]] = []

        if not self.csv_path.exists():
            return

        with open(
            self.csv_path,
            newline="",
            encoding="utf-8",
        ) as f:
            reader = csv.DictReader(f)

            for r in reader:
                self.rows.append(r)

    @staticmethod
    def _to_int(value):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime(value: str):
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(value)

            # Normalize naive timestamps to UTC so that all freshness
            # calculations use the same timezone-aware clock.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(timezone.utc)

        except (TypeError, ValueError):
            return None

    @classmethod
    def _days_since_updated(cls, updated_at: str):
        """
        Calculate freshness dynamically from the current time.

        IMPORTANT:
        This is intentionally NOT read from the CSV's historical
        days_since_updated value.
        """
        updated_dt = cls._parse_datetime(updated_at)

        if updated_dt is None:
            return None

        now = datetime.now(timezone.utc)

        # A future timestamp should not result in a negative freshness.
        if updated_dt > now:
            return 0

        return (now - updated_dt).days

    @classmethod
    def _with_dynamic_freshness(cls, row: Dict[str, Any]):
        """
        Return a copy of a listing row with a freshly calculated
        days_since_updated value. If the source provides an explicit
        updated_at timestamp, calculate days since from that value.
        Otherwise, fall back to the historical days_since_updated value
        stored in the CSV when present (so tests and historical dumps
        without updated_at continue to behave).
        """
        copy_row = dict(row)

        updated_at = copy_row.get("updated_at")

        if updated_at:
            copy_row["days_since_updated"] = cls._days_since_updated(
                updated_at
            )
        else:
            # Fall back to the CSV's stored days_since_updated when
            # there is no updated_at timestamp. Preserve unknown/empty
            # as None.
            csv_days = copy_row.get("days_since_updated")
            parsed = None
            try:
                if csv_days is not None and csv_days != "":
                    parsed = int(float(csv_days))
            except (TypeError, ValueError):
                parsed = None

            copy_row["days_since_updated"] = parsed

        return copy_row

    @classmethod
    def _normalize_active_ads_count(
        cls,
        row: Dict[str, Any],
    ):
        """
        Normalize active_ads_count to:

        - int when explicitly known
        - None when unknown/missing/invalid
        """
        copy_row = dict(row)

        value = copy_row.get("active_ads_count")

        if value is None:
            copy_row["active_ads_count"] = None
            return copy_row

        if isinstance(value, str) and value.strip() == "":
            copy_row["active_ads_count"] = None
            return copy_row

        normalized = cls._to_int(value)

        copy_row["active_ads_count"] = normalized

        return copy_row

    @classmethod
    def _normalize_for_api(
        cls,
        row: Dict[str, Any],
    ):
        """
        Normalize all derived API fields while keeping source data intact.
        """
        copy_row = cls._with_dynamic_freshness(row)
        copy_row = cls._normalize_active_ads_count(copy_row)

        return copy_row

    def query(self, params: Dict[str, str]) -> Dict[str, Any]:
        # Always reload latest CSV before serving a query so the API reflects
        # a recently regenerated business_listings.csv.
        self._load()

        results = list(self.rows)
        p = dict(params)

        # Smart Search:
        # Convert natural language to structured filters and use the same
        # filtering engine as normal filters.
        q = p.get("q")

        if q:
            parsed = parse_smart_query(q)

            for key, value in parsed.items():
                p.setdefault(key, value)

            # Only use naive text fallback when nothing structured
            # could be parsed.
            if not parsed:
                q_lower = q.lower()

                results = [
                    r
                    for r in results
                    if q_lower in (r.get("title") or "").lower()
                    or q_lower in (
                        r.get("description_full") or ""
                    ).lower()
                ]

        # Listing type
        if p.get("listing_type"):
            results = [
                r
                for r in results
                if r.get("listing_type") == p["listing_type"]
            ]

        # Property type
        if p.get("property_type"):
            results = [
                r
                for r in results
                if r.get("property_type") == p["property_type"]
            ]

        # Numeric helper
        def to_int(value):
            return self._to_int(value)

        # Area filters
        min_area = to_int(p.get("min_area"))
        max_area = to_int(p.get("max_area"))

        if min_area is not None:
            results = [
                r
                for r in results
                if (
                    to_int(r.get("area_sqm"))
                    is not None
                    and to_int(r.get("area_sqm")) >= min_area
                )
            ]

        if max_area is not None:
            results = [
                r
                for r in results
                if (
                    to_int(r.get("area_sqm"))
                    is not None
                    and to_int(r.get("area_sqm")) <= max_area
                )
            ]

        # Price filters
        min_price = to_int(p.get("min_price"))
        max_price = to_int(p.get("max_price"))

        if min_price is not None:
            results = [
                r
                for r in results
                if (
                    to_int(r.get("price"))
                    is not None
                    and to_int(r.get("price")) >= min_price
                )
            ]

        if max_price is not None:
            results = [
                r
                for r in results
                if (
                    to_int(r.get("price"))
                    is not None
                    and to_int(r.get("price")) <= max_price
                )
            ]

        # Bedrooms
        bedrooms_min = to_int(p.get("bedrooms_min"))

        if bedrooms_min is not None:
            results = [
                r
                for r in results
                if (
                    to_int(r.get("bedrooms"))
                    is not None
                    and to_int(r.get("bedrooms")) >= bedrooms_min
                )
            ]

        # Bathrooms
        bathrooms_min = to_int(p.get("bathrooms_min"))

        if bathrooms_min is not None:
            results = [
                r
                for r in results
                if (
                    to_int(r.get("bathrooms"))
                    is not None
                    and to_int(r.get("bathrooms")) >= bathrooms_min
                )
            ]

        # Completion status
        if p.get("completion_status"):
            results = [
                r
                for r in results
                if r.get("completion_status")
                == p["completion_status"]
            ]

        # Compound
        if p.get("compound"):
            compound_query = p["compound"].lower()

            results = [
                r
                for r in results
                if (
                    r.get("compound")
                    and compound_query
                    in r.get("compound").lower()
                )
            ]

        # ---------------------------------------------------------------
        # IMPORTANT:
        # Freshness is calculated NOW from updated_at.
        #
        # We intentionally do NOT trust any days_since_updated value
        # stored in the CSV.
        # ---------------------------------------------------------------

        freshness = to_int(p.get("freshness"))

        if freshness is not None:
            fresh_results = []

            for row in results:
                # Prefer authoritative updated_at if present; otherwise
                # fall back to the stored days_since_updated value from
                # the CSV (so historical datasets without updated_at
                # still support freshness filtering).
                if row.get("updated_at"):
                    days = self._days_since_updated(row.get("updated_at") or "")
                else:
                    days = to_int(row.get("days_since_updated"))

                if days is not None and days <= freshness:
                    fresh_results.append(row)

            results = fresh_results

        # Sorting
        sort = p.get("sort") or "newest"

        def parse_updated(value: str):
            parsed = self._parse_datetime(value)

            if parsed is None:
                return datetime.min.replace(
                    tzinfo=timezone.utc
                )

            return parsed

        if sort == "price_asc":
            results.sort(
                key=lambda r: to_int(r.get("price")) or 0
            )

        elif sort == "price_desc":
            results.sort(
                key=lambda r: -(to_int(r.get("price")) or 0)
            )

        elif sort == "area_asc":
            results.sort(
                key=lambda r: to_int(r.get("area_sqm")) or 0
            )

        elif sort == "area_desc":
            results.sort(
                key=lambda r: -(to_int(r.get("area_sqm")) or 0)
            )

        elif sort == "oldest":
            results.sort(
                key=lambda r: parse_updated(
                    r.get("updated_at") or ""
                )
            )

        else:
            # newest is based on source updated_at, not on days_since_updated
            results.sort(
                key=lambda r: parse_updated(
                    r.get("updated_at") or ""
                ),
                reverse=True,
            )

        total = len(results)

        # Pagination
        try:
            page = int(p.get("page") or 1)
        except (TypeError, ValueError):
            page = 1

        try:
            per_page = int(p.get("per_page") or 20)
        except (TypeError, ValueError):
            per_page = 20

        if page < 1:
            page = 1

        if per_page < 1 or per_page > 200:
            per_page = 20

        start = (page - 1) * per_page
        end = start + per_page

        page_results = results[start:end]

        total_pages = (
            (total + per_page - 1) // per_page
        )

        # API normalization:
        # - days_since_updated is recalculated RIGHT NOW
        # - active_ads_count is int or None
        normalized_results = [
            self._normalize_for_api(row)
            for row in page_results
        ]

        return {
            "count": len(normalized_results),
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "results": normalized_results,
        }

    def compounds(self, q: str = "") -> List[str]:
        self._load()

        values = set()

        for row in self.rows:
            compound = row.get("compound")

            if compound:
                values.add(compound)

        query_lower = q.lower()

        return sorted(
            [
                value
                for value in values
                if query_lower in value.lower()
            ]
        )

    def get(self, ad_id: str) -> Dict[str, Any]:
        self._load()

        for row in self.rows:
            if row.get("ad_id") == ad_id:
                return self._normalize_for_api(row)

        return {}