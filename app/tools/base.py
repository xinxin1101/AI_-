import re
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.core.config import Settings


class ToolExecutionError(RuntimeError):
    pass


class WeatherInput(BaseModel):
    location: str = Field(min_length=1, max_length=80)
    target_date: date


class ScenicInfoInput(BaseModel):
    scenic_name: str = Field(min_length=1, max_length=80)


class RouteInput(BaseModel):
    origin: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=80)
    mode: Literal["transit", "walking", "driving"] = "transit"


class ItineraryInput(BaseModel):
    days: int = Field(default=1, ge=1, le=7)
    interests: list[str] = Field(default_factory=list, max_length=8)


KNOWN_PLACES = (
    "龙脊梯田", "独秀峰王城", "两江四湖", "象鼻山", "桂林北站", "桂林站",
    "阳朔西街", "阳朔", "漓江", "象山", "桂林",
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ToolParameterGuard:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def text(self, value: str, field: str) -> str:
        normalized = re.sub(r"\s+", " ", value).strip(" ，。！？?；;：:")
        if not normalized:
            raise ToolExecutionError(f"{field} is empty")
        if len(normalized) > self.settings.tool_max_text_length:
            raise ToolExecutionError(f"{field} is too long")
        if _CONTROL_RE.search(normalized):
            raise ToolExecutionError(f"{field} contains control characters")
        if normalized.lower().startswith(("http://", "https://", "file://")):
            raise ToolExecutionError(f"{field} must be a place name, not a URL")
        return normalized

    def weather(self, value: WeatherInput) -> WeatherInput:
        value.location = self.text(value.location, "location")
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        # Open-Meteo forecast_days=16 covers today plus the next 15 days.
        if value.target_date < today or value.target_date > today + timedelta(days=15):
            raise ToolExecutionError(
                "weather date must be within the provider 16-day forecast window"
            )
        return value

    def scenic(self, value: ScenicInfoInput) -> ScenicInfoInput:
        value.scenic_name = self.text(value.scenic_name, "scenic_name")
        return value

    def route(self, value: RouteInput) -> RouteInput:
        value.origin = self.text(value.origin, "origin")
        value.destination = self.text(value.destination, "destination")
        if value.origin == value.destination:
            raise ToolExecutionError("origin and destination must be different")
        return value


def resolve_target_date(query: str) -> date:
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if "后天" in query:
        return today + timedelta(days=2)
    if "明天" in query:
        return today + timedelta(days=1)
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", query)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return today


def find_known_places(text: str) -> list[str]:
    """Return known Guilin-domain places in textual order, without duplicates."""
    matches: list[tuple[int, int, str]] = []
    for order, place in enumerate(KNOWN_PLACES):
        start = text.find(place)
        if start >= 0:
            matches.append((start, order, place))
    matches.sort()
    result: list[str] = []
    for _, _, place in matches:
        if place not in result:
            result.append(place)
    return result


def extract_known_place(query: str, default: str = "桂林") -> str:
    places = find_known_places(query)
    return places[0] if places else default


def parse_weather_input(query: str) -> WeatherInput:
    return WeatherInput(location=extract_known_place(query), target_date=resolve_target_date(query))


def parse_scenic_input(query: str) -> ScenicInfoInput:
    return ScenicInfoInput(scenic_name=extract_known_place(query, default="桂林景区"))


def parse_route_input(query: str) -> RouteInput:
    compact = re.sub(r"\s+", "", query)
    match = re.search(r"从(.+?)(?:到|去)(.+?)(?:怎么走|怎么去|如何去|如何走|坐什么|交通|路线|$)", compact)
    if not match:
        raise ToolExecutionError("route query must include origin and destination, e.g. 从桂林北站到阳朔西街怎么走")
    origin = match.group(1).strip("，。！？?；;：:")
    destination = match.group(2).strip("，。！？?；;：:")
    if "步行" in compact or "走路" in compact:
        mode = "walking"
    elif any(term in compact for term in ("驾车", "开车", "自驾", "打车")):
        mode = "driving"
    else:
        mode = "transit"
    return RouteInput(origin=origin, destination=destination, mode=mode)


def parse_itinerary_input(query: str) -> ItineraryInput:
    days = 1
    match = re.search(r"([1-7])\s*天", query)
    if match:
        days = int(match.group(1))
    else:
        cn = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
        match = re.search(r"([一二两三四五六七])天", query)
        if match:
            days = cn[match.group(1)]
    interests = [
        place for place in KNOWN_PLACES
        if place in query and place not in {"桂林", "桂林站", "桂林北站"}
    ]
    return ItineraryInput(days=days, interests=interests[:8])
