"""Logging configuration. Never attach tokens or message bodies."""

import logging
from contextvars import ContextVar

_correlation: ContextVar[str] = ContextVar("correlation", default="-")


def set_correlation(value: str | None) -> None:
    """Tag later log lines with an update id or a job id."""
    _correlation.set(value or "-")


class _ContextFilter(logging.Filter):
    """Copy the correlation id onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.corr = _correlation.get()
        return True


def setup_logging(level: str) -> None:
    """Configure the root logger once at process start."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s corr=%(corr)s %(message)s")
    )
    handler.addFilter(_ContextFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
