from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.core.config import Settings, get_settings
from app.observability.context import current_session_id, trace_id_var
from app.security.privacy import PrivacyRedactor


_RESERVED = set(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or get_settings()
        self.redactor = PrivacyRedactor(self.settings)

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self.redactor.text(record.getMessage()),
            "trace_id": trace_id_var.get(),
            "session_id": current_session_id(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = self.redactor.value(value)
        if record.exc_info:
            payload["exception"] = self.redactor.text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    handler = logging.StreamHandler()
    if settings.log_json:
        handler.setFormatter(JsonFormatter(settings))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.handlers.clear()
    root.addHandler(handler)
