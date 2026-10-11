from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Request
from app.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Stateful lifespan context manager to govern the lifetime of the connection-pooled
    AsyncClient, safely opening and tearing down active sockets.
    """
    limits = httpx.Limits(
        max_keepalive_connections=settings.HTTPX_MAX_KEEPALIVE, 
        max_connections=settings.HTTPX_MAX_CONNECTIONS
    )
    timeout = httpx.Timeout(
        settings.HTTPX_TIMEOUT, 
        connect=settings.HTTPX_CONNECT_TIMEOUT
    )
    
    app.state.http_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    yield
    # Gracefully close connections on shutdown
    await app.state.http_client.aclose()

async def get_http_client(request: Request) -> httpx.AsyncClient:
    """
    Dependency injection provider to yield the stateful pooled HTTPX client 
    to routers and controllers.
    """
    client = getattr(request.app.state, "http_client", None)
    if client is None:
        raise RuntimeError("The HTTPX AsyncClient has not been initialized inside the FastAPI state dictionary.")
    return client
