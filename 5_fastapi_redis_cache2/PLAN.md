# Plan: 5_fastapi_redis_cache2 — Real Redis + Product Management Backend

> Purpose: learning + production-ready intuition. Replace simulated/in-memory cache with real Docker Redis and rebuild the demo around product management.

## 0. Working directory & virtual environment (uv)

All commands run in `5_fastapi_redis_cache2/`:

```bash
pwd  # .../fastapi_projects/5_fastapi_redis_cache2
uv --version && python3 --version  # need Python >=3.11
uv venv .venv --python 3.12
source .venv/bin/activate
which python && python --version
uv pip install -e ".[dev]"
uv pip list | grep -E "fastapi|redis|pytest|httpx"
python -c "import fastapi, redis.asyncio, fastapi_cache; print('ok')"
```

Notes:
- Use `.venv` (already in `.gitignore`). Legacy `fastapi_redis_cache_env/` in old README is deprecated.
- Never commit `.venv/` or `.env`. VS Code → select `./.venv/bin/python`.
- Rebuild: `deactivate; rm -rf .venv; uv venv .venv; source .venv/bin/activate; uv pip install -e ".[dev]"`.
- If `pyproject.toml` changes, re-run install + `uv lock` / `uv sync`.

## 1. Baseline (current code)

- `app/main.py:create_app(use_redis)` → `lifespan_with_redis` / `lifespan_with_memory`.
- `app/core/cache.py`: `redis.asyncio.from_url + RedisBackend(fastapi-cache2)`, `city_key_builder → weather:{city}`, `X-Cache-Status`. InMemory only in tests.
- `app/services/weather_service.py`: dict + `asyncio.sleep(delay)` + `_call_count`.
- `app/api/routes_weather.py`: `GET /weather/{city} @cache(expire=settings.cache_ttl)` + `DELETE /cache/...`.
- `docker-compose.yml`: `redis:7-alpine`, appendonly, volume, healthcheck.
- Known bugs: `@cache(expire=settings.cache_ttl)` frozen at import; `clear_all_cache(namespace=prefix)` semantics differ Redis vs memory; no pool/timeout/retry/health.

## 2. Verify Docker Redis first

```bash
docker ps
docker compose ps
redis-cli -p 6379 PING  # expect PONG; else docker compose up -d
docker compose up -d
redis-cli INFO server | head
```

App check (after venv):
```bash
pytest -q            # memory baseline
curl -i http://localhost:8000/api/v1/weather/london  # twice → MISS then HIT
redis-cli KEYS "fastapi-cache:*"
redis-cli TTL "fastapi-cache:weather:london"
```

## 3. Core hardening

1. `app/core/config.py`: add `redis_pool_size, redis_socket_timeout, redis_retry_attempts, cache_ttl_product, cache_ttl_list, cache_ttl_search, simulated_db_delay, idempotency_ttl, rate_limit_max, rate_limit_window_s`.
2. New `app/core/redis.py`: single `redis.asyncio.ConnectionPool`, `get_client()`, FastAPI dep `get_redis()`, `ping_redis()`, `redis_info()`.
3. `app/main.py`: one Redis-only lifespan (PING fail-fast, `aclose()` on shutdown). Keep `use_redis=False` only as test fixture.
4. New `app/core/cache_keys.py`: versioned schemas:
   `v1:product:{id}`, `v1:products:list:{query-hash}`, `v1:products:search:{norm-q}`, `v1:product:{id}:views`, `v1:leaderboard:views` (ZSET), `v1:visitors:{id}` (HLL), `v1:cart:{user}` (Hash), `v1:idempotency:{key}`, `v1:ratelimit:{scope}:{window}`, `v1:lock:product:{id}`, `v1:autocomplete` (ZSET), `v1:product:{id}:tags` (SET).
5. Fix invalidation with `SCAN` + `UNLINK/DEL` (never `KEYS` in prod).

## 4. Product domain (replaces weather as primary demo)

Keep weather routes temporarily for regression, then deprecate.

- `app/schemas/product.py`: `ProductCreate/Update/Out`, list params `page,size,category,sort,q`.
- `app/services/product_service.py`: dict store + `asyncio.sleep(simulated_db_delay)` + call counters (same pattern as weather `_call_count`).
- `app/api/routes_products.py`:
  - `POST /api/v1/products` + `Idempotency-Key` (`SET NX EX`), invalidate list/search.
  - `GET /api/v1/products/{id}` manual cache-aside `GET → SETEX`, `X-Cache: HIT/MISS`.
  - `GET /api/v1/products` hashed normalized query key, short TTL (e.g. 15s).
  - `PUT/PATCH/DELETE /{id}` + `DEL` single + `SCAN DEL` list/search pattern.
  - `GET /search?q=` cached stub, `GET /featured` keeps one `@cache` decorator to contrast with manual.

## 5. Advanced Redis scenarios (one endpoint each)

1. **TTL strategies** — per-resource TTL, `GET /cache/ttl?key=` demo, `EXPIRE`/`TTL` via `redis-cli`.
2. **Stampede lock** — `SET NX PX` on hot product, `X-Lock: acquired/waited`.
3. **Counters/analytics** — `INCR product:{id}:views`, `ZINCRBY leaderboard`, `GET /analytics/top-viewed`, `PFADD/PFCOUNT` unique viewers.
4. **Cart (Hash+TTL)** — `HSET/HGETALL cart:{user}`, `EXPIRE 1800`, `POST/GET /cart/{user}[/items]`, `TTL` returned.
5. **Rate limit** — fixed-window `INCR+EXPIRE` on `POST /products` (e.g. 10/min/IP) → `429 + Retry-After`.
6. **Idempotency** — `SET key result NX EX 24h`, replay returns original.
7. **Pub/Sub invalidation** — publish `product.updated {id}` on write; subscriber logs/clears. Multi-instance note.
8. **Autocomplete/tags** — `ZADD autocomplete`, `SADD tags`, `GET /products/autocomplete?prefix=`.
9. **Health/metrics** — `GET /health` (PING+pool), `GET /ready`, `GET /metrics/redis` (`INFO`, `DBSIZE`, hit/miss counters).

Production notes for each: consistency, failure mode (fail-open reads vs fail-closed rate-limit/idempotency), cardinality guard, `SCAN` not `KEYS`.

## 6. Ops

- `docker-compose.yml`: add `app` service (`depends_on redis healthy`), env passthrough, optional `redis-commander` profile for UI. Keep volume.
- `Dockerfile`: install deps before `COPY .`, non-root user, `HEALTHCHECK CMD curl -f /health`.
- `.env.example`: document all vars. `README.md`: key table + `redis-cli` recipes + `docker stop redis` drill.

## 7. Tests (real Redis)

- `conftest.py`: `client_memory` (fast unit) + `client_redis` (DB 15, `FLUSHDB` per test, `pytest --redis` marker).
- Cover: hit/miss headers, invalidation on write, TTL expiry, lock single-flight, 429, idempotency replay, cart TTL, leaderboard order, SCAN invalidation.
- Run:
```bash
source .venv/bin/activate
docker compose up -d
pytest -q
pytest --redis -v -q
```

## 8. Build order

1. PLAN.md (this file) → 2. `.venv` → 3. Redis ping → 4. core hardening → 5. products CRUD → 6. advanced scenarios → 7. ops/docs → 8. tests/verify.
