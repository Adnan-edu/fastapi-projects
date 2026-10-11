#!/usr/bin/env bash
# Print container health + a SELECT 1 round-trip to confirm DB readiness.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "--- docker ps ---"
docker compose ps

echo
echo "--- postgres health ---"
docker inspect --format '{{.State.Health.Status}}' cursor_pg 2>/dev/null || echo "container not running"

echo
echo "--- SELECT 1 ---"
docker compose exec -T postgres psql -U "${POSTGRES_USER:-cursor}" -d "${POSTGRES_DB:-cursor_pagination}" -c "SELECT 1;"
