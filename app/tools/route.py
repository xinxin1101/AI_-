from datetime import datetime, timezone

import httpx

from app.agent.models import ToolEvidence
from app.core.config import Settings
from app.tools.amap import ensure_amap_success
from app.tools.base import RouteInput, ToolExecutionError
from app.tools.reliability import ProviderHTTPResult, ResilientHTTPClient


class MockRouteProvider:
    name = "mock"

    async def get(self, request: RouteInput) -> ToolEvidence:
        mode_cn = {"transit": "公共交通", "walking": "步行", "driving": "驾车"}[request.mode]
        return ToolEvidence(
            evidence_id="route_mock",
            tool_name="route",
            title=f"{request.origin} → {request.destination} {mode_cn}路线",
            content=(
                f"【开发模拟数据】从{request.origin}到{request.destination}采用{mode_cn}，"
                "模拟预计 70 分钟、约 65 公里。生产环境必须切换到地图 Provider。"
            ),
            source="P2 deterministic mock provider",
            observed_at=datetime.now(timezone.utc).isoformat(),
            freshness_class="realtime",
            confidence=1.0,
            metadata={
                "mock": True,
                "mode": request.mode,
                "provider_attempts": 1,
                "provider_latency_ms": 0.0,
                "circuit_state": "closed",
            },
        )


class AMapRouteProvider:
    name = "amap"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.http = ResilientHTTPClient(
            settings,
            "amap_route",
            transport=transport,
        )

    async def _geocode(
        self,
        place: str,
    ) -> tuple[str, str, ProviderHTTPResult]:
        result = await self.http.get_json(
            f"{self.settings.amap_base_url.rstrip('/')}/v3/geocode/geo",
            params={
                "key": self.settings.amap_api_key,
                "address": place,
                "city": self.settings.amap_region,
            },
        )
        payload = result.payload
        ensure_amap_success(payload, self.http, operation="geocode")
        geocodes = payload.get("geocodes") or []
        if not geocodes:
            self.http.record_provider_failure()
            raise ToolExecutionError(f"route place not found: {place}")
        first = geocodes[0]
        citycode = first.get("citycode") or self.settings.amap_citycode_default
        if isinstance(citycode, list):
            citycode = citycode[0] if citycode else self.settings.amap_citycode_default
        try:
            location = str(first["location"])
        except KeyError as exc:
            self.http.record_provider_failure()
            raise ToolExecutionError("amap geocode contract mismatch") from exc
        return location, str(citycode), result

    async def get(self, request: RouteInput) -> ToolEvidence:
        if not self.settings.amap_api_key:
            raise ToolExecutionError("AMAP_API_KEY is required for route provider")

        origin, city1, origin_result = await self._geocode(request.origin)
        destination, city2, destination_result = await self._geocode(request.destination)

        if request.mode == "transit":
            endpoint = "/v5/direction/transit/integrated"
            params = {
                "key": self.settings.amap_api_key,
                "origin": origin,
                "destination": destination,
                "city1": city1 or self.settings.amap_citycode_default,
                "city2": city2 or city1 or self.settings.amap_citycode_default,
                "strategy": 0,
            }
        elif request.mode == "walking":
            endpoint = "/v5/direction/walking"
            params = {
                "key": self.settings.amap_api_key,
                "origin": origin,
                "destination": destination,
            }
        else:
            endpoint = "/v5/direction/driving"
            params = {
                "key": self.settings.amap_api_key,
                "origin": origin,
                "destination": destination,
                "strategy": 32,
            }

        route_result = await self.http.get_json(
            f"{self.settings.amap_base_url.rstrip('/')}{endpoint}",
            params=params,
        )
        payload = route_result.payload
        ensure_amap_success(payload, self.http, operation="route_planning")

        route = payload.get("route") or {}
        candidates = route.get("paths") or route.get("transits") or []
        if not candidates:
            self.http.record_provider_failure()
            raise ToolExecutionError("route provider returned no route")
        first = candidates[0]
        duration = first.get("duration") or route.get("duration")
        distance = first.get("distance") or route.get("distance")
        try:
            duration_text = (
                f"约 {round(float(duration) / 60)} 分钟"
                if duration else "未返回耗时"
            )
            distance_text = (
                f"约 {round(float(distance) / 1000, 1)} 公里"
                if distance else "未返回距离"
            )
        except (TypeError, ValueError):
            duration_text, distance_text = "未返回耗时", "未返回距离"

        mode_cn = {"transit": "公共交通", "walking": "步行", "driving": "驾车"}[request.mode]
        operation_results = (origin_result, destination_result, route_result)
        # attempts represents retry depth for one provider operation. Summing the
        # three normal HTTP operations would make a healthy route call look retried.
        retry_depth = max(item.attempts for item in operation_results)
        total_latency = sum(item.latency_ms for item in operation_results)

        return ToolEvidence(
            evidence_id="amap_route",
            tool_name="route",
            title=f"{request.origin} → {request.destination} {mode_cn}路线",
            content=f"高德路径规划结果：{mode_cn}，{duration_text}，{distance_text}。",
            source="高德地图 路径规划 2.0",
            source_url="https://lbs.amap.com/api/webservice/guide/api/newroute",
            observed_at=datetime.now(timezone.utc).isoformat(),
            freshness_class="realtime",
            confidence=0.92,
            metadata={
                "origin": origin,
                "destination": destination,
                "mode": request.mode,
                "provider_attempts": retry_depth,
                "provider_latency_ms": round(total_latency, 2),
                "circuit_state": self.http.circuit_state,
            },
        )


def create_route_provider(settings: Settings):
    if settings.tool_mock_mode:
        return MockRouteProvider()
    if settings.route_provider == "amap":
        return AMapRouteProvider(settings)
    raise ValueError(f"Unsupported ROUTE_PROVIDER: {settings.route_provider}")
