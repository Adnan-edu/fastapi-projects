#!/bin/bash
set -e

cd "$(dirname "$0")"
source fastapienv/bin/activate

exec uvicorn app.main:app --loop asyncio --workers 1 --host 0.0.0.0 --port 8001
