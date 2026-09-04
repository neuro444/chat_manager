"""Read-only proxy to cost-api. GET-only, allowlisted paths, so the staff
dashboard can display cost data without exposing cost-api directly or its
write routes (price-flag edits, review runs, event ingestion)."""
import hmac

import httpx
from fastapi import APIRouter, Depends, Request, Response

import config
from api import require_dashboard_key

router = APIRouter(prefix="/cost", dependencies=[Depends(require_dashboard_key)])


@router.get("/pin-check")
def pin_check(pin: str = "") -> dict:
    """Checked server-side so the real PIN never ships in page source --
    still just a soft UX gate, not real security: anyone with dashboard
    access (the X-API-Key dependency above) can already reach every /cost/api
    route directly, PIN or not."""
    if not config.COST_MONITOR_PIN:
        return {"pin_required": False, "correct": True}
    return {"pin_required": True, "correct": hmac.compare_digest(pin, config.COST_MONITOR_PIN)}


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
    # the single-call drill-down: internal/calls/{id}
    if path.startswith("internal/calls/") and path.count("/") == 2:
        return True
    return False


@router.get("/api/{path:path}")
async def cost_proxy(path: str, request: Request) -> Response:
    if not _allowed(path):
        return Response(content='{"error":"not found"}', status_code=404, media_type="application/json")
    url = f"{config.COST_API_URL.rstrip('/')}/{path}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            upstream = await client.get(url, params=dict(request.query_params))
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/json"),
        )
    except httpx.RequestError:
        return Response(
            content='{"error":"cost monitoring unavailable"}',
            status_code=503,
            media_type="application/json",
        )
