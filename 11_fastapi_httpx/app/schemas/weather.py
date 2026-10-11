from pydantic import BaseModel
from typing import List, Optional

class CityWeatherResponse(BaseModel):
    """Data transfer object mapping individual city forecast results."""
    location: str
    temperature: Optional[float] = None
    windspeed: Optional[float] = None
    status: str
    error: Optional[str] = None

class BulkWeatherResponse(BaseModel):
    """Aggregated bulk response containing telemetry metrics."""
    benchmark: str
    elapsed_seconds: float
    results: List[CityWeatherResponse]
