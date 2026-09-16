from datetime import datetime, timezone

import httpx

from app.agent.models import ToolEvidence
from app.core.config import Settings
from app.tools.base import ToolExecutionError, WeatherInput


_WEATHER_CODES = {
    0: "晴", 1: "大部晴朗", 2: "局部多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "较强毛毛雨", 61: "小雨", 63: "中雨",
    65: "大雨", 71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨", 81: "较强阵雨",
    82: "强阵雨", 95: "雷暴",
}


class MockWeatherProvider:
    name = "mock"

    async def get(self, request: WeatherInput) -> ToolEvidence:
        return ToolEvidence(
            evidence_id="weather_mock",
            tool_name="weather",
            title=f"{request.location} {request.target_date.isoformat()} 天气",
            content=(
                f"【开发模拟数据】{request.location} 在 {request.target_date.isoformat()}："
                "多云，最高 27°C，最低 20°C，最大降水概率 30%。"
            ),
            source="P2 deterministic mock provider",
            observed_at=datetime.now(timezone.utc).isoformat(),
            freshness_class="realtime",
            confidence=1.0,
            metadata={"mock": True, "location": request.location},
        )


class OpenMeteoWeatherProvider:
    name = "open_meteo"
    _ALIASES = {"漓江": "桂林", "象鼻山": "桂林", "象山": "桂林", "两江四湖": "桂林", "龙脊梯田": "龙胜"}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def _geocode(self, client: httpx.AsyncClient, location: str) -> tuple[float, float, str]:
        search_name = self._ALIASES.get(location, location)
        response = await client.get(
            self.settings.open_meteo_geocoding_url,
            params={"name": search_name, "count": 1, "language": "zh", "countryCode": "CN"},
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            raise ToolExecutionError(f"weather location not found: {location}")
        first = results[0]
        return float(first["latitude"]), float(first["longitude"]), str(first.get("name") or location)

    async def get(self, request: WeatherInput) -> ToolEvidence:
        try:
            timeout = httpx.Timeout(self.settings.tool_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                lat, lon, resolved = await self._geocode(client, request.location)
                response = await client.get(
                    self.settings.open_meteo_forecast_url,
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                        "timezone": "Asia/Shanghai",
                        "forecast_days": 16,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ToolExecutionError("weather provider request failed") from exc

        daily = payload.get("daily") or {}
        dates = daily.get("time") or []
        target = request.target_date.isoformat()
        if target not in dates:
            raise ToolExecutionError("weather provider did not return requested date")
        idx = dates.index(target)
        code = int((daily.get("weather_code") or [0])[idx])
        tmax = (daily.get("temperature_2m_max") or [None])[idx]
        tmin = (daily.get("temperature_2m_min") or [None])[idx]
        rain = (daily.get("precipitation_probability_max") or [None])[idx]
        content = (
            f"{request.location}（天气定位：{resolved}）{target}：{_WEATHER_CODES.get(code, f'天气代码 {code}')}；"
            f"最高温 {tmax}°C，最低温 {tmin}°C，最大降水概率 {rain}%。"
        )
        return ToolEvidence(
            evidence_id=f"weather_{target}",
            tool_name="weather",
            title=f"{request.location} {target} 天气预报",
            content=content,
            source="Open-Meteo Forecast API",
            source_url="https://open-meteo.com/en/docs",
            observed_at=datetime.now(timezone.utc).isoformat(),
            freshness_class="realtime",
            confidence=0.95,
            metadata={"latitude": lat, "longitude": lon, "resolved_location": resolved},
        )


def create_weather_provider(settings: Settings):
    if settings.tool_mock_mode:
        return MockWeatherProvider()
    if settings.weather_provider == "open_meteo":
        return OpenMeteoWeatherProvider(settings)
    raise ValueError(f"Unsupported WEATHER_PROVIDER: {settings.weather_provider}")
