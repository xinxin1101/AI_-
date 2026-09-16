from typing import Any

from app.tools.base import ToolExecutionError
from app.tools.reliability import ResilientHTTPClient


def ensure_amap_success(
    payload: dict[str, Any],
    client: ResilientHTTPClient,
    *,
    operation: str,
) -> None:
    status = str(payload.get("status", ""))
    infocode = str(payload.get("infocode", ""))
    if status == "1" and (not infocode or infocode == "10000"):
        client.record_success()
        return

    client.record_provider_failure()
    info = str(payload.get("info") or "unknown provider error")
    raise ToolExecutionError(
        f"amap {operation} rejected request: {info} ({infocode or 'unknown'})"
    )
