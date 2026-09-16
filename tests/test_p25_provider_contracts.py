import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.core.config import Settings
from app.tools.base import (
    RouteInput,
    ScenicInfoInput,
    ToolExecutionError,
    ToolParameterGuard,
    WeatherInput,
)
from app.tools.reliability import ResilientHTTPClient
from app.tools.route import AMapRouteProvider
from app.tools.scenic import AMapScenicInfoProvider
from app.tools.weather import OpenMeteoWeatherProvider


def _settings(**overrides) -> Settings:
    values = {
        "tool_mock_mode": False,
        "tool_timeout_seconds": 2,
        "tool_retry_attempts": 1,
        "tool_retry_base_delay_seconds": 0,
        "tool_retry_max_delay_seconds": 0,
        "tool_circuit_failure_threshold": 2,
        "tool_circuit_recovery_seconds": 30,
        "amap_api_key": "test-key",
    }
    values.update(overrides)
    return Settings(**values)


def test_resilient_http_retries_transient_503_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"ok": True})

    client = ResilientHTTPClient(
        _settings(),
        "contract_test",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(client.get_json("https://provider.test/data"))

    assert result.payload == {"ok": True}
    assert result.attempts == 2
    assert calls == 2


def test_circuit_breaker_opens_after_consecutive_transient_failures() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "busy"})

    client = ResilientHTTPClient(
        _settings(tool_retry_attempts=0, tool_circuit_failure_threshold=2),
        "contract_test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ToolExecutionError):
        asyncio.run(client.get_json("https://provider.test/data"))
    with pytest.raises(ToolExecutionError):
        asyncio.run(client.get_json("https://provider.test/data"))

    assert client.circuit_state == "open"
    assert calls == 2

    with pytest.raises(ToolExecutionError, match="circuit breaker"):
        asyncio.run(client.get_json("https://provider.test/data"))
    assert calls == 2


def test_open_meteo_contract_is_parsed_and_carries_reliability_metadata() -> None:
    target = datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)
    geocode_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal geocode_calls
        if request.url.host == "geocoding-api.open-meteo.com":
            geocode_calls += 1
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "latitude": 29.922,
                            "longitude": 118.46802,
                            "name": "ambiguous-guilin",
                        }
                    ]
                },
            )
        if request.url.host == "api.open-meteo.com":
            assert request.url.params.get("latitude") == "25.2742"
            assert request.url.params.get("longitude") == "110.2964"
            return httpx.Response(
                200,
                json={
                    "daily": {
                        "time": [target.isoformat()],
                        "weather_code": [61],
                        "temperature_2m_max": [27.2],
                        "temperature_2m_min": [20.1],
                        "precipitation_probability_max": [65],
                    }
                },
            )
        return httpx.Response(404, json={})

    provider = OpenMeteoWeatherProvider(
        _settings(),
        transport=httpx.MockTransport(handler),
    )
    evidence = asyncio.run(
        provider.get(WeatherInput(location="漓江", target_date=target))
    )

    assert evidence.tool_name == "weather"
    assert "最大降水概率 65%" in evidence.content
    assert evidence.metadata["resolved_location"] == "桂林市"
    assert evidence.metadata["provider_attempts"] == 1
    assert evidence.metadata["circuit_state"] == "closed"
    assert geocode_calls == 0


def test_weather_guard_matches_open_meteo_sixteen_day_window() -> None:
    settings = _settings()
    guard = ToolParameterGuard(settings)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()

    guard.weather(WeatherInput(location="桂林", target_date=today + timedelta(days=15)))
    with pytest.raises(ToolExecutionError):
        guard.weather(
            WeatherInput(location="桂林", target_date=today + timedelta(days=16))
        )


def test_amap_scenic_contract_parses_business_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/place/text"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "pois": [
                    {
                        "id": "B001",
                        "name": "象鼻山景区",
                        "address": "桂林市象山区",
                        "location": "110.294,25.267",
                        "business": {
                            "opentime_today": "07:00-21:30",
                            "opentime_week": "周一至周日 07:00-21:30",
                            "tel": "0773-0000000",
                        },
                    }
                ],
            },
        )

    provider = AMapScenicInfoProvider(
        _settings(),
        transport=httpx.MockTransport(handler),
    )
    evidence = asyncio.run(provider.get(ScenicInfoInput(scenic_name="象鼻山")))

    assert evidence.source.startswith("高德地图")
    assert "07:00-21:30" in evidence.content
    assert evidence.metadata["provider_attempts"] == 1


def test_amap_business_error_is_not_blindly_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "status": "0",
                "info": "INVALID_USER_KEY",
                "infocode": "10001",
            },
        )

    provider = AMapScenicInfoProvider(
        _settings(tool_retry_attempts=3),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ToolExecutionError, match="INVALID_USER_KEY"):
        asyncio.run(provider.get(ScenicInfoInput(scenic_name="象鼻山")))

    assert calls == 1


def test_amap_route_contract_geocodes_then_plans_route() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v3/geocode/geo":
            address = request.url.params.get("address")
            location = (
                "110.301,25.331"
                if address == "桂林北站"
                else "110.294,25.267"
            )
            return httpx.Response(
                200,
                json={
                    "status": "1",
                    "info": "OK",
                    "infocode": "10000",
                    "geocodes": [
                        {"location": location, "citycode": "0773"}
                    ],
                },
            )
        if request.url.path == "/v5/direction/driving":
            return httpx.Response(
                200,
                json={
                    "status": "1",
                    "info": "OK",
                    "infocode": "10000",
                    "route": {
                        "paths": [
                            {"duration": "1500", "distance": "12500"}
                        ]
                    },
                },
            )
        return httpx.Response(404, json={})

    provider = AMapRouteProvider(
        _settings(),
        transport=httpx.MockTransport(handler),
    )
    evidence = asyncio.run(
        provider.get(
            RouteInput(
                origin="桂林北站",
                destination="象鼻山",
                mode="driving",
            )
        )
    )

    assert calls.count("/v3/geocode/geo") == 2
    assert "/v5/direction/driving" in calls
    assert "约 25 分钟" in evidence.content
    assert evidence.metadata["provider_attempts"] == 1
