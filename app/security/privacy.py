from __future__ import annotations

import re
from typing import Any

from app.core.config import Settings, get_settings


_EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])([A-Za-z0-9._%+-]*)(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_PHONE = re.compile(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)")
_CN_ID = re.compile(r"(?<!\d)(\d{6})(\d{8})(\d{3}[0-9Xx])(?!\d)")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_SECRET = re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,&;]+)")


class PrivacyRedactor:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def text(self, value: str | None) -> str | None:
        if value is None or not self.settings.pii_redaction_enabled:
            return value
        value = _EMAIL.sub(lambda m: f"{m.group(1)}***{m.group(3)}", value)
        value = _PHONE.sub(lambda m: f"{m.group(1)}****{m.group(3)}", value)
        value = _CN_ID.sub(lambda m: f"{m.group(1)}********{m.group(3)}", value)
        value = _BEARER.sub("Bearer ***", value)
        value = _SECRET.sub(lambda m: f"{m.group(1)}=***", value)
        return value

    def value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {str(key): self.value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.value(item) for item in value)
        return value


privacy_redactor = PrivacyRedactor()
