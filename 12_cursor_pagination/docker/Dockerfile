FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency manifests first for better caching
COPY pyproject.toml ./

# Install dependencies into a system venv-less environment
RUN uv pip install --system \
      fastapi \
      "uvicorn[standard]" \
      "sqlalchemy[asyncio]>=2.0.36" \
      asyncpg \
      pydantic \
      pydantic-settings \
      python-dotenv \
      structlog

COPY app ./app
COPY scripts ./scripts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
