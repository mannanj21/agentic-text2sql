import json
import logging
import re
import traceback
from contextvars import ContextVar
from typing import Any

# Context variables for tracing
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id_ctx: ContextVar[str | None] = ContextVar("run_id", default=None)

# Keys that should have their values redacted
REDACT_KEYS = {
    "password",
    "api_key",
    "authorization",
    "cookie",
    "token",
    "session_secret",
    "encryption_key",
}

# Regex for matching DSN strings (e.g., postgresql://user:pass@host)
DSN_REGEX = re.compile(r"([a-zA-Z0-9_+]+://[^:]+:)([^@]+)(@.+)")


def redact_string(s: str) -> str:
    """Redact passwords in DSN strings and other sensitive string patterns."""
    if not isinstance(s, str):
        return s

    # Redact DSN passwords
    s = DSN_REGEX.sub(r"\1***\3", s)
    return s


def redact_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive keys in a dictionary."""
    redacted: dict[str, Any] = {}
    for k, v in d.items():
        k_lower = str(k).lower()
        if any(redact_key in k_lower for redact_key in REDACT_KEYS):
            redacted[k] = "***"
        elif isinstance(v, dict):
            redacted[k] = redact_dict(v)
        elif isinstance(v, list):
            redacted[k] = [
                redact_dict(i) if isinstance(i, dict) else redact_string(str(i)) for i in v
            ]
        elif isinstance(v, str):
            redacted[k] = redact_string(v)
        else:
            redacted[k] = v
    return redacted


class JSONFormatter(logging.Formatter):
    """Structured JSON formatter with redaction and contextvars injection."""

    def format(self, record: logging.LogRecord) -> str:
        # Base log record dictionary
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": redact_string(record.getMessage()),
        }

        # Inject contextvars if present
        request_id = request_id_ctx.get()
        if request_id:
            log_data["request_id"] = request_id

        run_id = run_id_ctx.get()
        if run_id:
            log_data["run_id"] = run_id

        # Include exception info if present
        if record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info
            exc_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            log_data["exception"] = redact_string(exc_msg)

        # Include extra attributes
        # We need to filter out built-in LogRecord attributes
        extra = {}
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord("", 0, "", 0, "", (), None).__dict__:
                extra[key] = value

        if extra:
            log_data["extra"] = redact_dict(extra)

        return json.dumps(log_data)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured JSON logging globally."""
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    # Prevent uvicorn/fastapi from overriding our format
    logging.getLogger("uvicorn.access").handlers = [handler]
    logging.getLogger("uvicorn.access").propagate = False
    logging.getLogger("uvicorn.error").handlers = [handler]
    logging.getLogger("uvicorn.error").propagate = False
