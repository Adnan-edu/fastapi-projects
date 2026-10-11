FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv venv /app/.venv && \
    uv pip install -e ".[dev]"

COPY app/ app/

ENV PATH="/app/.venv/bin:$PATH"