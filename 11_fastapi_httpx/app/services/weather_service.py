import asyncio
from typing import Dict, Any, List
import httpx
from app.config import LOCATIONS
from app.schemas.weather import CityWeatherResponse

class WeatherService:
    """Service layer carrying out concurrent downstream API orchestration."""
    
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    @staticmethod
    def _get_url(lat: float, lon: float) -> str:
        return f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"

    async def fetch_city_weather(self, loc: Dict[str, Any]) -> CityWeatherResponse:
        """Fetch weather data for a singular city."""
        url = self._get_url(loc["lat"], loc["lon"])
        try:
            response = await self.client.get(url)
            data = response.json()
            return CityWeatherResponse(
                location=loc["name"],
                temperature=data.get("current_weather", {}).get("temperature"),
                windspeed=data.get("current_weather", {}).get("windspeed"),
                status="success"
            )
        except Exception as e:
            return CityWeatherResponse(
                location=loc["name"],
                status="failed",
                error=str(e)
            )

    async def get_all_weathers_concurrently(self) -> List[CityWeatherResponse]:
        """Fire weather query operations for all city locations concurrently."""
        tasks = [self.fetch_city_weather(loc) for loc in LOCATIONS]
        return await asyncio.gather(*tasks)
