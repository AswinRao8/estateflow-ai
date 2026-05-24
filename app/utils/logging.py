import logging
import sys
from app.config import Settings


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if settings.is_development:
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    else:
        # Structured single-line format for log aggregation in staging/prod.
        fmt = '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'

    formatter = logging.Formatter(fmt=fmt, datefmt="%Y-%m-%dT%H:%M:%S")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Suppress per-request access log lines — they're too noisy in dev.
    # uvicorn.error is intentionally left at root level so startup/shutdown
    # messages ("Application startup complete." etc.) remain visible.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
