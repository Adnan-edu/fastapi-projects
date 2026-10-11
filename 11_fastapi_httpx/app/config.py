from typing import List, Dict, Any

class Settings:
    PROJECT_NAME: str = "FastAPI Concurrent HTTPX Lab (Modular)"
    API_V1_STR: str = "/api/v1"
    
    # HTTPX Limits & Pool Sizes
    HTTPX_MAX_CONNECTIONS: int = 50
    HTTPX_MAX_KEEPALIVE: int = 20
    HTTPX_TIMEOUT: float = 10.0
    HTTPX_CONNECT_TIMEOUT: float = 5.0

settings = Settings()

# Coordinate sets for target locations
LOCATIONS: List[Dict[str, Any]] = [
    {"name": "Tokyo", "lat": 35.6895, "lon": 139.6917},
    {"name": "New York", "lat": 40.7128, "lon": -74.0060},
    {"name": "London", "lat": 51.5074, "lon": -0.1278},
    {"name": "Paris", "lat": 48.8566, "lon": 2.3522},
    {"name": "Sydney", "lat": -33.8688, "lon": 151.2093},
]
