# FastAPI Best Practices for Production APIs

FastAPI has rapidly become the go-to framework for building high-performance APIs in Python. However, moving from a prototype to a production-ready API requires careful attention to architecture, security, performance, and maintainability. After building and maintaining production FastAPI services handling thousands of requests per second, here are the essential practices I’ve learned.

## 1. Project Structure and Organization

A well-organized codebase is the foundation of maintainability. Here’s a production-ready structure:

```text
app/
├── main.py                 # Application entry point
├── core/
│   ├── config.py          # Configuration management
│   ├── security.py        # Authentication & authorization
│   └── dependencies.py    # Shared dependencies
├── api/
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── endpoints/
│   │   │   ├── users.py
│   │   │   ├── payments.py
│   │   │   └── transactions.py
│   │   └── router.py      # API version router
├── models/
│   ├── domain.py          # Business domain models
│   └── database.py        # SQLAlchemy models
├── schemas/
│   ├── requests.py        # Request models
│   └── responses.py       # Response models
├── services/
│   ├── user_service.py
│   └── payment_service.py
├── repositories/
│   └── user_repository.py
└── tests/
    ├── unit/
    └── integration/
```

This structure separates concerns clearly: API routing, business logic, data access, and configuration are all isolated, making the codebase easier to test and maintain.

## 2. Configuration Management

Never hardcode configuration values. Use Pydantic’s BaseSettings for type-safe, environment-aware configuration:

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "MyAPI"
    database_url: str
    redis_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # API rate limiting
    rate_limit_per_minute: int = 60
    
    # External services
    payment_gateway_url: str
    payment_gateway_key: str
    
    # Monitoring
    sentry_dsn: str | None = None
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

The @lru_cache() decorator ensures the settings are loaded only once, improving performance while maintaining testability.

## 3. Dependency Injection

Leverage FastAPI’s dependency injection system for database sessions, authentication, and shared logic:

```python
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Annotated

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)]
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

# Usage in endpoints
@router.get("/me")
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_user)]
):
    return current_user
```

## 4. Request Validation and Response Models

Pydantic models provide automatic validation and documentation. Always define explicit request and response schemas:

```python
from pydantic import BaseModel, Field, validator
from decimal import Decimal
from datetime import datetime

class TransactionRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Transaction amount")
    currency: str = Field(..., regex="^[A-Z]{3}$")
    recipient_account: str = Field(..., min_length=10, max_length=10)
    narration: str = Field(..., max_length=200)
    
    @validator('amount')
    def validate_amount(cls, v):
        if v > Decimal('1000000'):
            raise ValueError('Amount exceeds maximum limit')
        return v

class TransactionResponse(BaseModel):
    id: str
    amount: Decimal
    status: str
    reference: str
    created_at: datetime
    
    class Config:
        from_attributes = True  # For SQLAlchemy models
```

## 5. Error Handling and Custom Exceptions

Implement a consistent error handling strategy:

```python
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

class AppException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail

class InsufficientFundsException(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient funds for this transaction"
        )

class DuplicateTransactionException(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction with this reference already exists"
        )

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "details": exc.errors(),
            "timestamp": datetime.utcnow().isoformat()
        }
    )
```

## 6. Database Connection Management

Use connection pooling and proper session management:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,   # Recycle connections after 1 hour
    echo=False
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# For async operations
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)
```

## 7. API Versioning

Plan for evolution from day one:

```python
from fastapi import APIRouter

api_v1_router = APIRouter(prefix="/api/v1")

# Include all v1 endpoints
api_v1_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"]
)

api_v1_router.include_router(
    transactions.router,
    prefix="/transactions",
    tags=["transactions"]
)

# In main.py
app.include_router(api_v1_router)

# Future v2
api_v2_router = APIRouter(prefix="/api/v2")
# ... add v2 endpoints
app.include_router(api_v2_router)
```

## 8. Background Tasks and Async Processing

For long-running operations, use background tasks or task queues:

```python
from fastapi import BackgroundTasks
import httpx

async def send_notification(user_email: str, message: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://notification-service.com/send",
            json={"email": user_email, "message": message}
        )

@router.post("/transactions")
async def create_transaction(
    transaction: TransactionRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)]
):
    # Process transaction
    result = await process_transaction(transaction)
    
    # Send notification in background
    background_tasks.add_task(
        send_notification,
        current_user.email,
        f"Transaction {result.reference} completed"
    )
    
    return result
```

For heavier workloads, integrate Celery or RQ:

```python
from celery import Celery

celery_app = Celery(
    "tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

@celery_app.task
def process_bulk_transactions(transaction_ids: list[str]):
    # Heavy processing
    pass

@router.post("/transactions/bulk")
async def create_bulk_transactions(transactions: list[TransactionRequest]):
    # Queue for processing
    task = process_bulk_transactions.delay([t.id for t in transactions])
    return {"task_id": task.id, "status": "queued"}
```

## 9. Logging and Monitoring

Implement structured logging and monitoring:

```python
import logging
from pythonjsonlogger import jsonlogger
import time
from fastapi import Request

# Configure structured logging
logger = logging.getLogger()
handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(
    "%(asctime)s %(name)s %(levelname)s %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    logger.info(
        "Request started",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host
        }
    )
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    logger.info(
        "Request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration": duration
        }
    )
    
    return response
```

## 10. Rate Limiting

Protect your API from abuse:

```python
from fastapi import Request, HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/api/v1/data")
@limiter.limit("60/minute")
async def get_data(request: Request):
    return {"data": "value"}

# For authenticated users, use user ID as key
def get_user_id(request: Request):
    # Extract from JWT or session
    return request.state.user_id

@app.post("/api/v1/transactions")
@limiter.limit("10/minute", key_func=get_user_id)
async def create_transaction(request: Request, transaction: TransactionRequest):
    # Process transaction
    pass
```

## 11. Caching Strategies

Implement intelligent caching for frequently accessed data:

```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from redis import asyncio as aioredis

@app.on_event("startup")
async def startup():
    redis = aioredis.from_url(REDIS_URL)
    FastAPICache.init(RedisBackend(redis), prefix="api-cache")

@router.get("/exchange-rates")
@cache(expire=300)  # Cache for 5 minutes
async def get_exchange_rates():
    # This expensive operation runs only once per 5 minutes
    rates = await fetch_exchange_rates_from_external_api()
    return rates

# Manual cache control
from fastapi_cache import caches

async def invalidate_user_cache(user_id: str):
    cache = caches.get("default")
    await cache.delete(f"user:{user_id}")
```

## 12. Health Checks and Readiness Probes

Essential for Kubernetes and load balancers:

```python
from fastapi import status
from sqlalchemy import text

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "healthy"}

@app.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check(db: Annotated[Session, Depends(get_db)]):
    try:
        # Check database connectivity
        db.execute(text("SELECT 1"))
        
        # Check Redis
        redis_client = await aioredis.from_url(REDIS_URL)
        await redis_client.ping()
        
        return {
            "status": "ready",
            "database": "connected",
            "redis": "connected"
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )
```

## 13. Testing Strategy

Comprehensive testing ensures reliability:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Test database
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=test_engine)
    yield TestClient(app)
    Base.metadata.drop_all(bind=test_engine)

def test_create_transaction(client):
    response = client.post(
        "/api/v1/transactions",
        json={
            "amount": "100.00",
            "currency": "USD",
            "recipient_account": "1234567890",
            "narration": "Test payment"
        },
        headers={"Authorization": f"Bearer {test_token}"}
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
```

## 14. Security Best Practices

Security should be built-in, not bolted-on:

```python
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Never use ["*"] in production
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Trusted hosts
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["api.yourdomain.com", "*.yourdomain.com"]
)

# Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Security headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
```

## 15. Documentation

FastAPI’s automatic documentation is powerful, but enhance it:

```python
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Payment Processing API",
        version="1.0.0",
        description="Production-ready payment processing API",
        routes=app.routes,
    )
    
    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Rich endpoint documentation
@router.post(
    "/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new transaction",
    description="Process a payment transaction with validation and fraud checks",
    responses={
        201: {"description": "Transaction created successfully"},
        400: {"description": "Invalid transaction data"},
        401: {"description": "Authentication required"},
        409: {"description": "Duplicate transaction reference"},
    }
)
async def create_transaction(transaction: TransactionRequest):
    pass
```

## 16. Deployment Considerations

Optimize for production deployment:

```python
# main.py
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=4,  # Number of worker processes
        loop="uvloop",  # High-performance event loop
        log_config="logging_config.yaml",
        access_log=True,
        proxy_headers=True,  # Trust X-Forwarded-* headers
        forwarded_allow_ips="*",
    )
```

### Docker Configuration

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

## Conclusion

Building production-ready FastAPI applications requires attention to detail across multiple dimensions: architecture, performance, security, and operational concerns. These practices have been battle-tested in high-traffic production environments processing millions of transactions.

### Key Takeaways

- **Structure matters:** Organize your codebase for scale from day one
- **Configuration is code:** Treat settings with the same rigor as your business logic
- **Security by default:** Build authentication, rate limiting, and security headers into your foundation
- **Observability:** You can’t improve what you can’t measure
- **Test everything:** Unit tests, integration tests, and load tests prevent production surprises
- **Plan for failure:** Implement proper error handling, retries, and circuit breakers

FastAPI provides the tools; these practices ensure you use them effectively. Start with these foundations, iterate based on your specific needs, and continuously monitor and improve your APIs in production.
