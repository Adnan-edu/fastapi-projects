# Tech Stack

- Python >=3.11, FastAPI >=0.115.0, uvicorn[standard] >=0.32.0, asyncpg >=0.30.0, pydantic-settings >=2.6.0
- Dev: pytest >=8.0.0, pytest-asyncio >=0.24.0 (asyncio_mode=auto), httpx >=0.27.0 (ASGITransport), anyio >=4.0.0
- Build: hatchling (`packages=["app"]`), `pyproject.toml` with `[tool.pytest.ini_options] testpaths=["tests"]`
- DB: Postgres 16-alpine via docker-compose (`productuser/productpass/productdb`, port 5432, volume `postgres_data`, healthcheck `pg_isready`)
- Config: `pydantic-settings BaseSettings`, `env_file=.env`, defaults match `.env.example` (`DATABASE_URL=postgres://...`)
- No ORM / no Alembic: schema via `migrations/001_create_products_table.sql` + duplicate `CREATE_TABLES_SQL` in `db.py` executed on `connect_db()`
