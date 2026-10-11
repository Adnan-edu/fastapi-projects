# ⚡ FastAPI Concurrent HTTPX — Modular Production App

A focused, production-grade FastAPI project demonstrating the most efficient HTTPX pattern:
**`@asynccontextmanager` lifespan connection pooling + `asyncio.gather` for concurrent HTTP requests.**

Inspired by: *[My FastAPI App Was Slow. This One Fix Made It 80% Faster](https://medium.com/@inprogrammer/my-fastapi-app-was-slow-this-one-fix-made-it-80-faster-1f3b3905e20d?sk=eef45e313a8d3fb5a1ceec8cf82b42ff)*

---

## 🗂️ Project Structure

```
11_fastapi_httpx/
│
├── main.py                        # ← App entry point (assembles routers + lifespan)
│
├── app/                           # Core application package
│   ├── config.py                  # Settings, HTTPX limits, location coordinates
│   ├── core/
│   │   └── http_client.py         # @asynccontextmanager lifespan + DI provider
│   ├── schemas/
│   │   └── weather.py             # Pydantic response models
│   ├── services/
│   │   └── weather_service.py     # Business logic: asyncio.gather concurrent fetches
│   └── api/
│       └── v1/
│           └── weather.py         # Route handler with Depends() injection
│
├── httpx_concurrent.py            # Thin entrypoint wrapper (re-exports from main)
├── pyproject.toml                 # Project dependencies
└── httpx_venv/                    # Project-specific virtual environment
```

---

## 🔑 Core Concept: The Two Key Patterns

### 1. `@asynccontextmanager` Lifespan — Connection Pool Setup

Defined in [`app/core/http_client.py`](app/core/http_client.py), the lifespan creates **one shared `httpx.AsyncClient`** when the server starts and gracefully closes it on shutdown.

```python
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP: runs once when the server boots ---
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
    timeout = httpx.Timeout(10.0, connect=5.0)
    app.state.http_client = httpx.AsyncClient(limits=limits, timeout=timeout)

    yield  # ← Server is live and handling requests here

    # --- SHUTDOWN: runs once when the server stops ---
    await app.state.http_client.aclose()
```

The client is registered in `main.py`:
```python
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
```

**Why this matters:**
- Creating a new `httpx.AsyncClient` per request = new TCP/SSL handshake every time (~100–300ms overhead)
- One shared client = connections stay open (Keep-Alive), no repeated handshakes

---

### 2. `asyncio.gather` — Concurrent Fetches Over the Pooled Client

Defined in [`app/services/weather_service.py`](app/services/weather_service.py), all 5 city weather requests fire **simultaneously** instead of sequentially:

```python
import asyncio

async def get_all_weathers_concurrently(self) -> List[CityWeatherResponse]:
    tasks = [self.fetch_city_weather(loc) for loc in LOCATIONS]
    return await asyncio.gather(*tasks)
```

**Why this matters:**

| Approach | Time for 5 requests |
|---|---|
| Sequential (one by one) | `T1 + T2 + T3 + T4 + T5` ≈ 2–4 seconds |
| Concurrent (`asyncio.gather`) | `max(T1…T5)` ≈ 0.3–0.5 seconds |

---

## 🚀 Running the Application

### Prerequisites
- Python 3.12+
- `uv` package manager

### Setup

```bash
# 1. Clone / navigate to project root
cd 11_fastapi_httpx

# 2. Create and activate the virtual environment
uv venv httpx_venv
source httpx_venv/bin/activate   # macOS/Linux
# httpx_venv\Scripts\activate    # Windows

# 3. Install dependencies
uv pip install fastapi uvicorn httpx requests pytest pytest-asyncio orjson
```

### Start the Server

> ⚠️ **Always run from the project root** (the directory containing `main.py`), not from inside `app/`.

```bash
# Activate environment first
source httpx_venv/bin/activate

# Run the standalone app
uvicorn main:app --reload
```

Server starts at: **http://127.0.0.1:8000**

---

## 📡 Available Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Root — welcome message + endpoint map |
| `GET` | `/api/v1/weather` | Fetches 5 cities concurrently via pooled client |
| `GET` | `/docs` | Interactive Swagger UI |
| `GET` | `/redoc` | ReDoc API documentation |

### Sample Response from `GET /api/v1/weather`

```json
{
  "benchmark": "Modular Async Concurrent (Pooled Client + Dependency Injection)",
  "elapsed_seconds": 0.312,
  "results": [
    {"location": "Tokyo",    "temperature": 22.1, "windspeed": 8.4,  "status": "success"},
    {"location": "New York", "temperature": 18.5, "windspeed": 14.2, "status": "success"},
    {"location": "London",   "temperature": 14.0, "windspeed": 19.1, "status": "success"},
    {"location": "Paris",    "temperature": 16.3, "windspeed": 11.7, "status": "success"},
    {"location": "Sydney",   "temperature": 12.8, "windspeed": 9.3,  "status": "success"}
  ]
}
```

---

## 🔗 How the Layers Connect

```
main.py
  └── registers lifespan (app.core.http_client)
  └── mounts router    (app.api.v1.weather)
              │
              └── Depends(get_http_client)  ← pulls client from app.state
              └── WeatherService(client)    ← injects client into service
                        │
                        └── asyncio.gather(fetch × 5)  ← fires concurrently
                                  │
                                  └── Open-Meteo Weather API (public, free, no key)
```

---

## 🧪 Running Tests

The test suite uses `pytest` with fully mocked external API calls — no internet required:

```bash
source httpx_venv/bin/activate
pytest test_main.py -v
```

---

## 🎯 Key Takeaways

1. **Use `@asynccontextmanager` lifespan** to initialize heavy resources (HTTP clients, DB pools) once at startup and clean them up at shutdown.
2. **Store shared resources in `app.state`** and expose them via `Depends()` for clean dependency injection into route handlers.
3. **Use `asyncio.gather`** to fire multiple independent async requests concurrently — total time becomes the slowest single request, not the sum of all.
