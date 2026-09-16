from datetime import datetime, timezone

import httpx

from app.agent.models import ToolEvidence
from app.core.config import Settings
from app.tools.base import RouteInput, ToolExecutionError


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
            metadata={"mock": True, "mode": request.mode},
        )


class AMapRouteProvider:
    name = "amap"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def _geocode(self, client: httpx.AsyncClient, place: str) -> tuple[str, str]:
        response = await client.get(
            f"{self.settings.amap_base_url.rstrip('/')}/v3/geocode/geo",
            params={"key": self.settings.amap_api_key, "address": place, "city": self.settings.amap_region},
        )
        response.raise_for_status()
        geocodes = response.json().get("geocodes") or []
        if not geocodes:
            raise ToolExecutionError(f"route place not found: {place}")
        first = geocodes[0]
        citycode = first.get("citycode") or ""
        if isinstance(citycode, list):
            citycode = citycode[0] if citycode else ""
        return str(first["location"]), str(citycode)

    async def get(self, request: RouteInput) -> ToolEvidence:
        if not self.settings.amap_api_key:
            raise ToolExecutionError("AMAP_API_KEY is required for route provider")
        try:
            async with httpx.AsyncClient(timeout=self.settings.tool_timeout_seconds) as client:
                origin, city1 = await self._geocode(client, request.origin)
                destination, city2 = await self._geocode(client, request.destination)
                if request.mode == "transit":
                    endpoint = "/v5/direction/transit/integrated"
                    params = {
                        "key": self.settings.amap_api_key,
                        "origin": origin,
                        "destination": destination,
                        "city1": city1,
                        "city2": city2 or city1,
                        "strategy": 0,
                    }
                elif request.mode == "walking":
                    endpoint = "/v5/direction/walking"
                    params = {"key": self.settings.amap_api_key, "origin": origin, "destination": destination}
                else:
                    endpoint = "/v5/direction/driving"
                    params = {
                        "key": self.settings.amap_api_key,
                        "origin": origin,
                        "destination": destination,
                        "strategy": 32,
                    }
                response = await client.get(f"{self.settings.amap_base_url.rstrip('/')}{endpoint}", params=params)
                response.raise_for_status()
                payload = response.json()
        except ToolExecutionError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ToolExecutionError("route provider request failed") from exc

        route = payload.get("route") or {}
        candidates = route.get("paths") or route.get("transits") or []
        if not candidates:
            raise ToolExecutionError("route provider returned no route")
        first = candidates[0]
        duration = first.get("duration") or route.get("duration")
        distance = first.get("distance") or route.get("distance")
        try:
            duration_text = f"约 {round(float(duration) / 60)} 分钟" if duration else "未返回耗时"
            distance_text = f"约 {round(float(distance) / 1000, 1)} 公里" if distance else "未返回距离"
        except (TypeError, ValueError):
            duration_text, distance_text = "未返回耗时", "未返回距离"
        mode_cn = {"transit": "公共交通", "walking": "步行", "driving": "驾车"}[request.mode]
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
            metadata={"origin": origin, "destination": destination, "mode": request.mode},
        )


def create_route_provider(settings: Settings):
    if settings.tool_mock_mode:
        return MockRouteProvider()
    if settings.route_provider == "amap":
        return AMapRouteProvider(settings)
    raise ValueError(f"Unsupported ROUTE_PROVIDER: {settings.route_provider}")
