# Core — fastapi_asyncpg_database_driver

- Tutorial Product Inventory API: FastAPI + asyncpg raw SQL + connection pooling, no ORM.
- Source map:
  - `app/main.py`: `create_app()` factory + `lifespan` (connect_db/close_db), router include
  - `app/core/config.py`: Settings (`APP_NAME`, `DATABASE_URL`)
  - `app/core/db.py`: module-global `pool: asyncpg.Pool|None`, `connect_db()`, `close_db()`, `get_pool()`, `CREATE_TABLES_SQL`
  - `app/api/routes_products.py`: `prefix=/api/v1/products`, 6 endpoints (CRUD + bulk-stock-update)
  - `app/schemas/product.py`: ProductCreate/Update/Response/ListResponse, StockUpdateItem/BulkStockUpdate
  - `app/repositories/product_repository.py`: raw SQL, `$1`-style params, `dict(row)` conversion
  - `app/services/product_service.py`: business logic, `model_dump(exclude_unset=True)` for PATCH, `model_validate`
  - `migrations/001_create_products_table.sql`: products table + 2 indexes, mounted to docker init
  - `tests/conftest.py`, `tests/test_products.py`: real-DB integration tests
- Layer invariant: Route -> Service -> Repository -> asyncpg Pool -> Postgres. Never import pool in routes/services; only repository via `get_pool()`.
- DB invariant: single shared pool (min_size=2,max_size=10) created in lifespan/startup, closed on shutdown. `pool.fetch/fetchrow/execute` auto acquire/release; `pool.acquire()+conn.transaction()` only for transactions (bulk_update_stock).
- Return-type invariant: repository returns `dict|list[dict]` (via `dict(asyncpg.Record)`), service returns Pydantic models.
- For stack/build/test details see `mem:tech_stack`, `mem:suggested_commands`. For style see `mem:conventions`. For done-checks see `mem:task_completion`.
