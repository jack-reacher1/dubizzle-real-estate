import os

import httpx
from fastapi import APIRouter, Header, HTTPException

router = APIRouter()


@router.api_route("/api/cron/scrape", methods=["GET", "POST"])
async def cron_scrape(authorization: str | None = Header(default=None)):
    expected = os.getenv("CRON_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="Cron secret is not configured")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    worker_url = os.getenv("WORKER_URL")
    worker_secret = os.getenv("WORKER_TRIGGER_SECRET")
    if not worker_url or not worker_secret:
        raise HTTPException(status_code=503, detail="Worker trigger is not configured")

    try:
        async with httpx.AsyncClient(timeout=float(os.getenv("WORKER_TRIGGER_TIMEOUT_SECONDS", "10"))) as client:
            response = await client.get(
                f"{worker_url.rstrip('/')}/run",
                headers={"Authorization": f"Bearer {worker_secret}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Worker trigger failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return {"status": "accepted", "worker": response.json()}
