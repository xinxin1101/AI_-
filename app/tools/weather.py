from datetime import datetime, timezone

import httpx

from app.agent.models import ToolEvidence
from app.core.config import Settings
from app.tools.base import ToolExecutionError, WeatherInput
from app.tools.reliability import ProviderHTTPResult, ResilientHTTPClient


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
            metadata={
                "mock": True,
                "location": request.location,
                "provider_attempts": 1,
                "provider_latency_ms": 0.0,
                "circuit_state": "closed",
            },
        )


class OpenMeteoWeatherProvider:
    name = "open_meteo"
    _ALIASES = {
        "漓江": "桂林",
        "象鼻山": "桂林",
        "象山": "桂林",
        "两江四湖": "桂林",
        "龙脊梯田": "龙胜",
    }
    # The application is Guilin-domain specific. Open-Meteo fuzzy geocoding has
    # resolved both 桂林 and 龙胜 to unrelated Chinese places during live RC runs,
    # so known tourism locations use verified canonical coordinates.
    _KNOWN_COORDINATES = {
        "桂林": (25.2742, 110.2964, "桂林市"),
        "龙胜": (25.770717, 110.140047, "龙脊梯田风景名胜区"),
    }
    _MAX_PROVIDER_TIMEOUT_SECONDS = 5.0

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        # Weather is retried by ResilientHTTPClient. Bounding each attempt prevents
        # a single public-provider stall from consuming the full generic 15s Tool
        # timeout before retrying. Other providers retain the configured timeout.
        weather_settings = settings.model_copy(
            update={
                "tool_timeout_seconds": min(
                    settings.tool_timeout_seconds,
                    self._MAX_PROVIDER_TIMEOUT_SECONDS,
                )
            }
        )
        self.http = ResilientHTTPClient(
            weather_settings,
            self.name,
            transport=transport,
        )

    def _validate_payload(self, payload: dict, operation: str) -> None:
        if payload.get("error"):
            self.http.record_provider_failure()
            reason = payload.get("reason") or payload.get("message") or "provider error"
            raise ToolExecutionError(f"open_meteo {operation} rejected request: {reason}")

    async def _geocode(
        self,
        location: str,
    ) -> tuple[float, float, str, ProviderHTTPResult | None]:
        search_name = self._ALIASES.get(location, location)
        known = self._KNOWN_COORDINATES.get(search_name)
        if known is not None:
            lat, lon, resolved = known
            return lat, lon, resolved, None

        result = await self.http.get_json(
            self.settings.open_meteo_geocoding_url,
            params={
                "name": search_name,
                "count": 5,
                "language": "zh",
                "countryCode": "CN",
            },
        )
        self._validate_payload(result.payload, "geocoding")
        results = result.payload.get("results") or []
        if not results:
            self.http.record_provider_failure()
            raise ToolExecutionError(f"weather location not found: {location}")

        def normalized(value: object) -> str:
            text = str(value or "").strip().replace(" ", "")
            return text[:-1] if text.endswith("市") else text

        exact = next(
            (item for item in results if normalized(item.get("name")) == normalized(search_name)),
            None,
        )
        first = exact or results[0]
        try:
            lat = float(first["latitude"])
            lon = float(first["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            self.http.record_provider_failure()
            raise ToolExecutionError("open_meteo geocoding contract mismatch") from exc
        self.http.record_success()
        return lat, lon, str(first.get("name") or location), result

    async def get(self, request: WeatherInput) -> ToolEvidence:
        lat, lon, resolved, geocode_result = await self._geocode(request.location)
        forecast_result = await self.http.get_json(
            self.settings.open_meteo_forecast_url,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max"
                ),
                "timezone": "Asia/Shanghai",
                "forecast_days": 16,
            },
        )
        self._validate_payload(forecast_result.payload, "forecast")
        daily = forecast_result.payload.get("daily") or {}
        dates = daily.get("time") or []
        target = request.target_date.isoformat()
        if target not in dates:
            self.http.record_provider_failure()
            raise ToolExecutionError("weather provider did not return requested date")
        idx = dates.index(target)
        try:
            code = int(daily["weather_code"][idx])
            tmax = daily["temperature_2m_max"][idx]
            tmin = daily["temperature_2m_min"][idx]
            rain = daily["precipitation_probability_max"][idx]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            self.http.record_provider_failure()
            raise ToolExecutionError("open_meteo forecast contract mismatch") from exc
        self.http.record_success()

        operation_results = [forecast_result]
        if geocode_result is not None:
            operation_results.append(geocode_result)
        provider_attempts = max(item.attempts for item in operation_results)
        provider_latency = sum(item.latency_ms for item in operation_results)

        content = (
            f"{request.location}（天气定位：{resolved}）{target}："
            f"{_WEATHER_CODES.get(code, f'天气代码 {code}')}；"
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
            metadata={
                "latitude": lat,
                "longitude": lon,
                "resolved_location": resolved,
                # attempts is retry depth per provider operation, not the number of
                # distinct HTTP operations used to fulfill a tool invocation.
                "provider_attempts": provider_attempts,
                "provider_latency_ms": round(provider_latency, 2),
                "circuit_state": self.http.circuit_state,
            },
        )


def create_weather_provider(settings: Settings):
    if settings.tool_mock_mode:
        return MockWeatherProvider()
    if settings.weather_provider == "open_meteo":
        return OpenMeteoWeatherProvider(settings)
    raise ValueError(f"Unsupported WEATHER_PROVIDER: {settings.weather_provider}")
