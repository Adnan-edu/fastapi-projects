import asyncio
import time
from datetime import datetime, timezone

from app.core.config import settings

WEATHER_DATA: dict[str, dict] = {
    "london": {
        "temperature_c": 14,
        "condition": "Cloudy",
        "humidity": 78,
        "wind_speed_kph": 20,
    },
    "tokyo": {
        "temperature_c": 22,
        "condition": "Sunny",
        "humidity": 55,
        "wind_speed_kph": 10,
    },
    "new york": {
        "temperature_c": 18,
        "condition": "Partly Cloudy",
        "humidity": 62,
        "wind_speed_kph": 25,
    },
    "paris": {
        "temperature_c": 16,
        "condition": "Rainy",
        "humidity": 82,
        "wind_speed_kph": 15,
    },
    "sydney": {
        "temperature_c": 25,
        "condition": "Sunny",
        "humidity": 45,
        "wind_speed_kph": 12,
    },
    "berlin": {
        "temperature_c": 12,
        "condition": "Overcast",
        "humidity": 70,
        "wind_speed_kph": 18,
    },
}

_call_count: dict[str, int] = {}


def _reset_call_count() -> None:
    global _call_count
    _call_count = {}


def get_call_count(city: str) -> int:
    return _call_count.get(city.lower(), 0)


async def get_weather(city: str) -> dict:
    city_lower = city.lower()
    _call_count[city_lower] = _call_count.get(city_lower, 0) + 1

    await asyncio.sleep(settings.weather_simulated_delay)

    preset = WEATHER_DATA.get(city_lower, {
        "temperature_c": 20,
        "condition": "Clear",
        "humidity": 50,
        "wind_speed_kph": 8,
    })

    return {
        "city": city.title(),
        "temperature_c": preset["temperature_c"],
        "condition": preset["condition"],
        "humidity": preset["humidity"],
        "wind_speed_kph": preset["wind_speed_kph"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def timed_get_weather(city: str) -> dict:
    start = time.perf_counter()
    result = await get_weather(city)
    elapsed_ms = (time.perf_counter() - start) * 1000
    result["response_time_ms"] = round(elapsed_ms, 2)
    return result