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

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    logger.info(
        "Starting %s v%s [%s]",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )
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
