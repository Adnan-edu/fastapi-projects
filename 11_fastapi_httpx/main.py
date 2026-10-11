from fastapi import FastAPI
from app.core.http_client import lifespan
from app.api.v1.weather import router as weather_router
from app.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

# Mount versioned API routers
app.include_router(weather_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    """Application root health and documentation endpoint."""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}!",
        "docs": "/docs",
        "endpoints": {
            "weather_concurrent": f"{settings.API_V1_STR}/weather"
        }
    }
