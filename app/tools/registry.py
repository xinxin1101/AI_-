from app.core.config import Settings, get_settings
from app.tools.itinerary import ItineraryPlannerTool
from app.tools.route import create_route_provider
from app.tools.scenic import create_scenic_provider
from app.tools.weather import create_weather_provider


class ToolRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.weather = create_weather_provider(self.settings)
        self.scenic = create_scenic_provider(self.settings)
        self.route = create_route_provider(self.settings)
        self.itinerary = ItineraryPlannerTool()


tool_registry = ToolRegistry()
