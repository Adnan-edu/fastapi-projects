#!/usr/bin/env bash
# Start the PostgreSQL container (and the API container if you want it).
# Reads .env for credentials and waits for the DB to be ready.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "[start] .env not found — copying from .env.example"
  cp .env.example .env
fi

echo "[start] Bringing up postgres ..."
docker compose up -d postgres

echo "[start] Waiting for postgres to be healthy ..."
for _ in {1..30}; do
  status=$(docker inspect --format '{{.State.Health.Status}}' cursor_pg 2>/dev/null || echo "starting")
  if [[ "$status" == "healthy" ]]; then
    echo "[start] postgres is healthy."
    exit 0
  fi
  sleep 1
done

echo "[start] postgres did not become healthy in 30s." >&2
docker compose logs --tail=50 postgres >&2
exit 1
