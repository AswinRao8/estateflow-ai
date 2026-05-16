from datetime import datetime, UTC
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import check_database_connection
from app.models.base import APIResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=APIResponse[dict], summary="Liveness check")
def health_check():
    """Returns 200 when the application process is alive.

    Includes a market summary so operators can confirm the correct
    market configuration is active for this deployment.
    """
    settings = get_settings()
    return APIResponse(data={
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(UTC).isoformat(),
        "market": {
            "currency": f"{settings.market.currency_symbol} ({settings.market.currency_code})",
            "area_unit": settings.market.area_unit,
            "timezone": settings.market.timezone,
            "locale": settings.market.communication_locale,
        },
    })


@router.get("/ready", summary="Readiness check")
async def readiness_check():
    """Returns 200 when ready to serve traffic, 503 when a critical dependency is down.

    In testing environments the DB check is skipped so local test runs
    don't require a live database. In all other environments a real connection
    attempt is made — a failed ping returns 503 so load balancers withhold traffic.
    """
    settings = get_settings()
    checks: dict[str, str] = {}

    if settings.is_testing:
        checks["database"] = "skipped"
    else:
        reachable = await check_database_connection()
        checks["database"] = "ok" if reachable else "unreachable"

    all_ok = all(v in ("ok", "skipped") for v in checks.values())
    payload = APIResponse(data={
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
        "timestamp": datetime.now(UTC).isoformat(),
    })

    if not all_ok:
        return JSONResponse(status_code=503, content=payload.model_dump())
    return payload
