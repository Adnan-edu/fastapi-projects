#!/usr/bin/env bash
# Stop the stack without removing volumes (data persists in the `pgdata` volume).
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose stop
