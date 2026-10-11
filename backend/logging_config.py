"""
Structured logging + request-correlation helpers.

* `LOG_FORMAT=json` (default) emits one JSON object per line -- greppable and ready for
  log shippers. `LOG_FORMAT=text` gives a human-friendly format for local debugging.
* A `request_id` context variable is attached to every log record emitted while a request
  is being handled, so a failing model call, retrieval query, database error or artifact
  render can be traced back to one HTTP request via the `X-Request-ID` response header.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def configure_logging(log_format: str = "json", level: str = "INFO") -> None:
    """Idempotently (re)configures the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    if log_format == "text":
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s [%(request_id)s]: %(message)s")
        )
        handler.addFilter(_RequestIdFilter())
    else:
        handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_lenny_handler", False):
            root.removeHandler(existing)
    handler._lenny_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
