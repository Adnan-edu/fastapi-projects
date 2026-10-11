from fastapi import APIRouter
from pydantic import BaseModel

from fastapi_cache.decorator import cache

from app.core.cache import clear_all_cache, clear_city_cache
from app.core.config import settings
from app.services.weather_service import timed_get_weather

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])


class WeatherResponse(BaseModel):
    city: str
    temperature_c: int
    condition: str
    humidity: int
    wind_speed_kph: int
    fetched_at: str
    response_time_ms: float


class CacheClearResponse(BaseModel):
    message: str


class CacheClearCityResponse(BaseModel):
    message: str
    city: str


@router.get("/{city}", response_model=WeatherResponse)
@cache(expire=settings.cache_ttl, namespace="weather")
async def get_weather(city: str):
    return await timed_get_weather(city)


@router.delete("/cache/{city}", response_model=CacheClearCityResponse)
async def clear_cache_for_city(city: str):
    success = await clear_city_cache(city)
    if success:
        return CacheClearCityResponse(
            message=f"Cache cleared for {city.title()}",
            city=city.title(),
        )
    return CacheClearCityResponse(
        message=f"Failed to clear cache for {city.title()}",
        city=city.title(),
    )


@router.delete("/cache", response_model=CacheClearResponse)
async def clear_all_weather_cache():
    success = await clear_all_cache()
    if success:
        return CacheClearResponse(message="All weather cache cleared")
    return CacheClearResponse(message="Failed to clear cache")