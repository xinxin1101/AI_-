import argparse
import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.tools.base import RouteInput, ScenicInfoInput, WeatherInput
from app.tools.route import AMapRouteProvider
from app.tools.scenic import AMapScenicInfoProvider
from app.tools.weather import OpenMeteoWeatherProvider


async def _run_open_meteo(settings: Settings) -> dict:
    provider = OpenMeteoWeatherProvider(settings)
    target = datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)
    evidence = await provider.get(
        WeatherInput(location="桂林", target_date=target)
    )
    return {
        "provider": "open_meteo",
        "ok": True,
        "title": evidence.title,
        "metadata": evidence.metadata,
    }


async def _run_amap(settings: Settings) -> list[dict]:
    scenic = AMapScenicInfoProvider(settings)
    route = AMapRouteProvider(settings)

    scenic_evidence = await scenic.get(ScenicInfoInput(scenic_name="象鼻山"))
    route_evidence = await route.get(
        RouteInput(
            origin="桂林北站",
            destination="象鼻山",
            mode="driving",
        )
    )
    return [
        {
            "provider": "amap_poi",
            "ok": True,
            "title": scenic_evidence.title,
            "metadata": scenic_evidence.metadata,
        },
        {
            "provider": "amap_route",
            "ok": True,
            "title": route_evidence.title,
            "metadata": route_evidence.metadata,
        },
    ]


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run opt-in live provider smoke checks.")
    parser.add_argument("--open-meteo", action="store_true")
    parser.add_argument("--amap", action="store_true")
    args = parser.parse_args()

    if not args.open_meteo and not args.amap:
        args.open_meteo = True

    settings = Settings(tool_mock_mode=False)
    results: list[dict] = []

    if args.open_meteo:
        results.append(await _run_open_meteo(settings))

    if args.amap:
        if not settings.amap_api_key:
            raise SystemExit("AMAP_API_KEY is required for --amap live smoke")
        results.extend(await _run_amap(settings))

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
