"""Structured logging: one line per record, correlated to its request (observability spec).

Stdlib only (design.md Decision 1): a ``Formatter`` that writes one JSON object per record,
a ``Filter`` that stamps the request context onto every record, and ``configure_logging``,
called once from ``create_app``. Emitters anywhere in the codebase keep using
``logging.getLogger(__name__)``; correlation arrives as record *attributes*, never inside
the message text, so existing ``caplog`` assertions on message text are unaffected.
"""

import datetime as dt
import json
import logging
import sys
from typing import Any

from backend.core import request_context
from backend.core.config import Settings

AUDIT_LOGGER = "backend.tools.audit"
CONTEXT_FIELDS = ("request_id", "user_id", "child_profile_id")

TEXT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s [%(request_id)s]: %(message)s"

# Attributes every LogRecord carries; anything else on the record is an `extra` field.
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"} | set(CONTEXT_FIELDS)


class RequestContextFilter(logging.Filter):
    """Copy the request's correlation values onto the record (null outside a request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_context.get_request_id()
        record.user_id = request_context.get_user_id()
        record.child_profile_id = request_context.get_child_profile_id()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per record: fixed keys, the context fields, then every extra."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            payload[field] = getattr(record, field, None)
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = record.stack_info
        return json.dumps(payload, default=str, ensure_ascii=False)


def _formatter(log_format: str) -> logging.Formatter:
    return JsonFormatter() if log_format == "json" else logging.Formatter(TEXT_FORMAT)


def configure_logging(settings: Settings | None) -> None:
    """Install the one root handler (and the optional audit file handler). Idempotent.

    ``settings`` may be ``None`` when the application database is unconfigured (the app
    still boots and reports it on ``/health``); logging then uses the defaults.
    """
    log_format = settings.log_format if settings is not None else "json"
    level = settings.log_level if settings is not None else "INFO"
    audit_path = settings.audit_log_path if settings is not None else None

    # Only handlers this function installed are replaced: pytest's caplog handler, or a
    # host's own handler, must survive a repeated create_app().
    root = logging.getLogger()
    _remove_ours(root)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_formatter(log_format))
    handler.addFilter(RequestContextFilter())
    _mark_ours(handler)
    root.addHandler(handler)
    root.setLevel(level)

    audit = logging.getLogger(AUDIT_LOGGER)
    _remove_ours(audit)
    if audit_path:
        # Hard rule 8 records get their own sink; propagate=False keeps them out of stdout
        # so they are written exactly once.
        file_handler = logging.FileHandler(audit_path, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        file_handler.addFilter(RequestContextFilter())
        _mark_ours(file_handler)
        audit.addHandler(file_handler)
        audit.propagate = False
    else:
        audit.propagate = True


_OURS = "_nutrition_app_handler"


def _mark_ours(handler: logging.Handler) -> None:
    setattr(handler, _OURS, True)


def _remove_ours(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, _OURS, False):
            logger.removeHandler(handler)
            handler.close()
