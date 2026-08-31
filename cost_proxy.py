"""Read-only proxy to the cost-api. GET-only, allowlisted paths, so the
dashboard can display cost data without exposing cost-api or its write routes."""
import httpx
from fastapi import APIRouter, Depends, Request, Response

import config
from api import require_api_key

router = APIRouter(prefix="/cost/api", dependencies=[Depends(require_api_key)])

_ALLOWED = {
    "internal/costs/daily",
    "internal/calls",
    "internal/reviews",
    "internal/price-checks",
    "internal/price-flags",
}


def _allowed(path: str) -> bool:
    if path in _ALLOWED:
        return True
    # allow the single-call drill-down: internal/calls/{id}
    if path.startswith("internal/calls/") and path.count("/") == 2:
        return True
    return False


@router.get("/{path:path}")
async def cost_proxy(path: str, request: Request) -> Response:
    if not _allowed(path):
        return Response(content='{"error":"not found"}', status_code=404, media_type="application/json")
    url = f"{config.COST_API_URL.rstrip('/')}/{path}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            upstream = await client.get(url, params=dict(request.query_params))
        return Response(content=upstream.content, status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type", "application/json"))
    except Exception:
        return Response(content='{"error":"cost monitoring unavailable"}', status_code=503,
                        media_type="application/json")
