# Conventions

- Layering: routes thin (HTTP+404 via `HTTPException`), services orchestrate + validate, repositories only place with SQL strings
- SQL: positional params `$1,$2...` (asyncpg style, never `%s`/`:name`); `RETURNING ...` on INSERT/UPDATE/DELETE to avoid extra SELECT; explicit column lists, never `SELECT *` in app code
- Records: `dict(row)` via `_record_to_dict()` immediately; never leak `asyncpg.Record` past repository
- Schemas: `ProductCreate` (required name 1-200, price Decimal gt=0, stock ge=0), `ProductUpdate` all-optional + `exclude_unset=True`, `ProductResponse(from_attributes=True)`
- Updates: read-modify-write in `update_product()` (fetch existing, merge Nones, single UPDATE with `updated_at=NOW()`); empty PATCH returns current row
- Transactions: `async with pool.acquire() as conn: async with conn.transaction():` loop `conn.execute()` — used in `bulk_update_stock`
- Naming: `*_service` suffix in services, repository fns match entity ops, router fns mirror service names
- Types: `X | None` (py3.11 union), `Decimal` for price, `async def` throughout DB path
