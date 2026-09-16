from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.config import Settings
from app.tools.base import (
    RouteInput,
    ToolExecutionError,
    ToolParameterGuard,
    parse_itinerary_input,
    parse_route_input,
    parse_weather_input,
)


def test_tool_parsers_extract_weather_route_and_itinerary() -> None:
    weather = parse_weather_input("明天去漓江会下雨吗？")
    assert weather.location == "漓江"
    assert weather.target_date > datetime.now(ZoneInfo("Asia/Shanghai")).date()

    route = parse_route_input("从桂林北站到阳朔西街怎么走？")
    assert route.origin == "桂林北站"
    assert route.destination == "阳朔西街"
    assert route.mode == "transit"

    itinerary = parse_itinerary_input("桂林两天怎么玩，想去漓江和阳朔")
    assert itinerary.days == 2
    assert "漓江" in itinerary.interests
    assert "阳朔" in itinerary.interests


def test_tool_parameter_guard_rejects_urls_and_same_route_endpoint() -> None:
    guard = ToolParameterGuard(Settings(tool_mock_mode=True))
    with pytest.raises(ToolExecutionError):
        guard.text("https://example.com", "location")
    with pytest.raises(ToolExecutionError):
        guard.route(RouteInput(origin="桂林站", destination="桂林站"))
