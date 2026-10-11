import time
from fastapi import APIRouter, Depends
import httpx
from app.core.http_client import get_http_client
from app.services.weather_service import WeatherService
from app.schemas.weather import BulkWeatherResponse

router = APIRouter(prefix="/weather", tags=["weather"])

@router.get("", response_model=BulkWeatherResponse)
async def get_concurrent_weather(
    client: httpx.AsyncClient = Depends(get_http_client)
) -> BulkWeatherResponse:
    """
    Modular route that fetches weather forecasts for major global cities concurrently.
    Dependency Injection fetches the shared connection pooled AsyncClient.
    """
    start_time = time.perf_counter()
    
    # Instantiate the service with the injected shared client
    service = WeatherService(client=client)
    results = await service.get_all_weathers_concurrently()
    
    elapsed_time = time.perf_counter() - start_time
    return BulkWeatherResponse(
        benchmark="Modular Async Concurrent (Pooled Client + Dependency Injection)",
        elapsed_seconds=elapsed_time,
        results=results
    )
