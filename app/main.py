import asyncio
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.utils.logging import configure_logging, get_logger
from app.models.base import ErrorResponse
from app.routers import health_router
from app.routers import lead_router
from app.routers import listing_router
from app.routers import whatsapp_router
from app.routers import agent_router
from app.routers import session_router
from app.routers import admin_router
from app.routers import dashboard_router
from app.routers import debug_router

logger = get_logger(__name__)

_STARTUP_DB_TIMEOUT = 5.0  # seconds — warn but don't block startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------------ #
    # STARTUP — each step is logged explicitly so hangs are immediately
    # visible. No step is allowed to block indefinitely: external checks
    # use asyncio.wait_for with _STARTUP_DB_TIMEOUT.
    # ------------------------------------------------------------------ #
    try:
        # Step 1: settings + logging
        logger.debug("[STARTUP 1/3] Configuring logging...")
        settings = get_settings()
        configure_logging(settings)
        logger.info(
            "[STARTUP 1/3] Logging configured | app=%s v%s | env=%s | level=%s",
            settings.app_name,
            settings.app_version,
            settings.environment,
            settings.log_level,
        )

        # Step 2: DB health check (non-blocking — a failure here is a warning,
        # not a reason to refuse startup; the app degrades gracefully).
        logger.info("[STARTUP 2/3] Checking database connectivity (timeout=%ss)...", _STARTUP_DB_TIMEOUT)
        try:
            from app.database import check_database_connection
            reachable = await asyncio.wait_for(
                check_database_connection(), timeout=_STARTUP_DB_TIMEOUT
            )
            if reachable:
                logger.info("[STARTUP 2/3] Database reachable")
            else:
                logger.warning(
                    "[STARTUP 2/3] Database unreachable — continuing; "
                    "requests requiring DB will fail until it is available"
                )
        except asyncio.TimeoutError:
            logger.error(
                "[STARTUP 2/3] Database health check timed out after %ss — "
                "continuing; check DATABASE_URL and network connectivity",
                _STARTUP_DB_TIMEOUT,
            )
        except Exception:
            logger.error(
                "[STARTUP 2/3] Database health check raised an exception — "
                "continuing; traceback follows\n%s",
                traceback.format_exc(),
            )

        # Step 3: ready
        logger.info(
            "[STARTUP 3/3] %s v%s [%s] is ready",
            settings.app_name,
            settings.app_version,
            settings.environment,
        )

    except Exception:
        # Any unexpected error during startup is logged with full traceback
        # and re-raised so uvicorn exits cleanly rather than hanging silently.
        logger.critical(
            "STARTUP FAILED — unhandled exception:\n%s",
            traceback.format_exc(),
        )
        raise

    yield

    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI-assisted real estate operational infrastructure.",
        # Disable interactive docs in production — they expose the API surface.
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    _register_routers(app, settings.api_prefix)
    _register_exception_handlers(app)

    return app


def _register_routers(app: FastAPI, api_prefix: str) -> None:
    # Health endpoints sit outside the versioned prefix so infrastructure
    # tooling (load balancers, k8s probes) can reach them without auth.
    app.include_router(health_router.router)

    # All business API endpoints are versioned under /api/v1.
    app.include_router(lead_router.router, prefix=api_prefix)
    app.include_router(listing_router.router, prefix=api_prefix)
    app.include_router(agent_router.router, prefix=api_prefix)
    app.include_router(session_router.router, prefix=api_prefix)
    app.include_router(admin_router.router, prefix=api_prefix)

    # WhatsApp webhook sits outside the versioned prefix because
    # the provider URL is configured externally and changing it
    # requires updating the provider dashboard — not just code.
    app.include_router(whatsapp_router.router)

    # Agent dashboard — served at /dashboard (no API prefix, no versioning).
    app.include_router(dashboard_router.router)

    # Raw-SQL diagnostic endpoints — development only, never mounted in production.
    if get_settings().is_development:
        app.include_router(debug_router.router)
        logger.info("Debug router mounted at /debug (development mode)")


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        logger.warning("HTTP %s at %s: %s", exc.status_code, request.url.path, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse.of(
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        field = ".".join(str(loc) for loc in first.get("loc", []))
        message = first.get("msg", "Validation error")
        logger.warning("Validation error at %s: %s", request.url.path, errors)
        return JSONResponse(
            status_code=422,
            content=ErrorResponse.of(
                code="VALIDATION_ERROR",
                message=message,
                field=field or None,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception at %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse.of(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred.",
            ).model_dump(),
        )


app = create_app()
