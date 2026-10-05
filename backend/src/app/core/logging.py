"""Logs estructurados (JSON fuera de local) con request_id, org y usuario."""

import logging
import sys

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    renderer: structlog.typing.Processor = (
        structlog.dev.ConsoleRenderer()
        if settings.env in ("local", "test")
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
