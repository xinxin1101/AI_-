from datetime import datetime, timezone

import httpx

from app.agent.models import ToolEvidence
from app.core.config import Settings
from app.tools.amap import ensure_amap_success
from app.tools.base import ScenicInfoInput, ToolExecutionError
from app.tools.reliability import ResilientHTTPClient


class MockScenicInfoProvider:
    name = "mock"

    async def get(self, request: ScenicInfoInput) -> ToolEvidence:
        return ToolEvidence(
            evidence_id="scenic_mock",
            tool_name="scenic_info",
            title=f"{request.scenic_name} 实时景点信息",
            content=(
                f"【开发模拟数据】{request.scenic_name} 当前状态为正常开放；"
                "模拟开放时段 07:00-22:00。生产环境必须切换到实时 Provider。"
            ),
            source="P2 deterministic mock provider",
            observed_at=datetime.now(timezone.utc).isoformat(),
            freshness_class="realtime",
            confidence=1.0,
            metadata={
                "mock": True,
                "provider_attempts": 1,
                "provider_latency_ms": 0.0,
                "circuit_state": "closed",
            },
        )


class AMapScenicInfoProvider:
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
            "amap_scenic",
            transport=transport,
        )

    async def get(self, request: ScenicInfoInput) -> ToolEvidence:
        if not self.settings.amap_api_key:
            raise ToolExecutionError("AMAP_API_KEY is required for scenic_info provider")

        result = await self.http.get_json(
            f"{self.settings.amap_base_url.rstrip('/')}/v5/place/text",
            params={
                "key": self.settings.amap_api_key,
                "keywords": request.scenic_name,
                "region": self.settings.amap_region,
                "city_limit": "true",
                "show_fields": "business",
                "page_size": 5,
            },
        )
        payload = result.payload
        ensure_amap_success(payload, self.http, operation="poi_search")

        pois = payload.get("pois") or []
        if not pois:
            self.http.record_provider_failure()
            raise ToolExecutionError(f"scenic POI not found: {request.scenic_name}")
        poi = pois[0]
        business = poi.get("business") or {}
        today = business.get("opentime_today") or "未返回结构化今日营业时间"
        week = business.get("opentime_week") or "未返回周营业时间"
        address = poi.get("address") or "未返回地址"
        tel = business.get("tel") or poi.get("tel") or "未返回电话"
        cost = business.get("cost")
        cost_text = f"；参考人均/费用字段：{cost}" if cost else ""

        return ToolEvidence(
            evidence_id=f"amap_poi_{poi.get('id', 'unknown')}",
            tool_name="scenic_info",
            title=f"{poi.get('name') or request.scenic_name} POI 实时信息",
            content=(
                f"地址：{address}；今日营业时间：{today}；"
                f"周营业时间：{week}；联系电话：{tel}{cost_text}。"
            ),
            source="高德地图 Web服务 POI 2.0",
            source_url="https://lbs.amap.com/api/webservice/guide/api-advanced/newpoisearch",
            observed_at=datetime.now(timezone.utc).isoformat(),
            freshness_class="realtime",
            confidence=0.90,
            metadata={
                "poi_id": poi.get("id"),
                "location": poi.get("location"),
                "provider_attempts": result.attempts,
                "provider_latency_ms": round(result.latency_ms, 2),
                "circuit_state": self.http.circuit_state,
            },
        )


def create_scenic_provider(settings: Settings):
    if settings.tool_mock_mode:
        return MockScenicInfoProvider()
    if settings.scenic_provider == "amap":
        return AMapScenicInfoProvider(settings)
    raise ValueError(f"Unsupported SCENIC_PROVIDER: {settings.scenic_provider}")
