from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from services.listings import ListingsService
from pathlib import Path
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

try:
    import asyncpg
except Exception:
    asyncpg = None

APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8010"))
APP_DEFAULT_PER_PAGE = int(os.getenv("APP_DEFAULT_PER_PAGE", "20"))
APP_MAX_PER_PAGE = int(os.getenv("APP_MAX_PER_PAGE", "200"))
ASYNCPG_STATEMENT_CACHE_SIZE = int(os.getenv("ASYNCPG_STATEMENT_CACHE_SIZE", "0"))

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
service = ListingsService()

@app.on_event("startup")
async def startup_event():
    database_url = os.getenv("DATABASE_URL")
    if database_url and asyncpg:
        # Supabase uses PgBouncer by default; asyncpg prepared statement caching must be disabled
        # or the app will hit "prepared statement already exists" on repeated queries.
        app.state.db_pool = await asyncpg.create_pool(
            dsn=database_url,
            min_size=1,
            max_size=5,
            statement_cache_size=ASYNCPG_STATEMENT_CACHE_SIZE,
        )
    else:
        app.state.db_pool = None


@app.on_event("shutdown")
async def shutdown_event():
    pool = getattr(app.state, "db_pool", None)
    if pool:
        await pool.close()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Prefer redesigned template if present, otherwise fall back to index.html
    tpl_new = Path("templates") / "index_redesign.html"
    tpl_default = Path("templates") / "index.html"
    if tpl_new.exists():
        return HTMLResponse(content=tpl_new.read_text(encoding="utf-8"))
    if tpl_default.exists():
        return HTMLResponse(content=tpl_default.read_text(encoding="utf-8"))
    raise HTTPException(status_code=500, detail="UI template missing")


def _validate_positive_int(name: str, value: str, min_value: int = 0, max_value: int | None = None) -> int:
    try:
        v = int(value)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid value for '{name}': must be an integer")
    if v < min_value:
        raise HTTPException(status_code=400, detail=f"Invalid value for '{name}': must be >= {min_value}")
    if max_value is not None and v > max_value:
        raise HTTPException(status_code=400, detail=f"Invalid value for '{name}': must be <= {max_value}")
    return v


ALLOWED_SORTS = {"newest", "oldest", "price_asc", "price_desc", "area_asc", "area_desc"}


@app.get("/api/listings")
async def api_listings(request: Request):
    # Strict validation of known public query parameters.
    # Empty form values are treated as absent so the browser can send all
    # optional controls without triggering a 400 for blank inputs.
    raw = {k: v for k, v in request.query_params.items()}
    params: dict[str, str] = {}

    def has_value(key: str) -> bool:
        return key in raw and raw[key] not in (None, "")

    # allowed simple passthrough params
    for key in ("q", "listing_type", "property_type", "compound", "completion_status"):
        if has_value(key):
            params[key] = raw[key]

    # numeric filters
    for key, name in (("min_price", "min_price"), ("max_price", "max_price"),
                      ("min_area", "min_area"), ("max_area", "max_area"),
                      ("bedrooms_min", "bedrooms_min"), ("bathrooms_min", "bathrooms_min")):
        if has_value(key):
            v = raw[key]
            _ = _validate_positive_int(name, v, min_value=0)
            params[key] = v

    # pagination
    for key, name in (("page", "page"), ("per_page", "per_page")):
        if has_value(key):
            v = raw[key]
            if key == "page":
                _ = _validate_positive_int(name, v, min_value=1)
            else:
                _ = _validate_positive_int(name, v, min_value=1, max_value=APP_MAX_PER_PAGE)
            params[key] = v

    # sort
    if has_value("sort"):
        v = raw["sort"]
        if v not in ALLOWED_SORTS:
            raise HTTPException(status_code=400, detail=f"Invalid sort option: {v}")
        params["sort"] = v

    # freshness (optional) - must be positive integer days
    if has_value("freshness"):
        v = raw["freshness"]
        _ = _validate_positive_int("freshness", v, min_value=1)
        params["freshness"] = v

    # reject unknown params to avoid silent acceptance
    known = {"q", "listing_type", "property_type", "compound", "completion_status",
             "min_price", "max_price", "min_area", "max_area", "bedrooms_min", "bathrooms_min",
             "page", "per_page", "sort", "freshness"}
    unknown = set(raw.keys()) - known
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown query parameters: {', '.join(sorted(unknown))}")

    try:
        result = service.query(params)
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/compounds")
async def api_compounds(q: str = ""):
    try:
        return JSONResponse(content=service.compounds(q))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/listing/{ad_id}")
async def api_listing(ad_id: str):
    r = service.get(ad_id)
    if not r:
        raise HTTPException(status_code=404, detail="Listing not found")
    return JSONResponse(content=r)

@app.get("/api/meta")
async def api_meta():
    """Return scrape metadata. When a DATABASE_URL is configured and asyncpg is available,
    read the metadata from the scrape_meta table in Postgres (key='scrape_status').
    Otherwise, fall back to the legacy local file data/scrape_status.json.
    """
    status_file = Path("data/scrape_status.json")
    local_data = None

    if status_file.exists():
        try:
            local_data = json.loads(status_file.read_text(encoding="utf-8"))
        except Exception:
            local_data = None

    pool = getattr(app.state, "db_pool", None)

    if pool:
        try:
            row = await pool.fetchrow("SELECT value FROM scrape_meta WHERE key = $1", "scrape_status")
            if row:
                # asyncpg maps jsonb -> Python types.
                database_data = row["value"]
                database_time = database_data.get("last_successful_scrape_at")
                local_time = (local_data or {}).get("last_successful_scrape_at")

                if database_time and (
                    not local_time
                    or datetime.fromisoformat(database_time)
                    >= datetime.fromisoformat(local_time)
                ):
                    return JSONResponse(content=database_data)
        except Exception:
            # Keep the local status available when Postgres is unreachable.
            pass

    # fallback to file-based status (legacy)
    if local_data is None:
        return JSONResponse({
            "status": "unknown",
            "last_successful_scrape_at": None,
        })

    return JSONResponse(content=local_data)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=APP_HOST, port=APP_PORT, reload=True)
    