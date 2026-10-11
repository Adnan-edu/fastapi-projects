# FastAPI AsyncPG: Raw SQL Database Driver

A tutorial-friendly Product Inventory API that teaches high-performance async database drivers in FastAPI using **asyncpg** with raw SQL and connection pooling — no ORM layer.

## What You'll Learn

- What database drivers are and why they matter
- Why `asyncpg` is fast (binary protocol, prepared statements, zero-copy)
- How connection pooling works beneath ORMs
- Raw SQL vs ORM trade-offs
- The repository pattern for clean separation
- How FastAPI startup/shutdown manages DB pools
- How the `databases` library differs from using `asyncpg` directly
- Transaction handling with asyncpg

## Quick Start

```bash
# Start PostgreSQL
docker compose up -d

# Create and activate virtual environment
uv venv fastapi_asyncpg_env
source fastapi_asyncpg_env/bin/activate

# Install dependencies
uv pip install fastapi uvicorn[standard] asyncpg pydantic-settings pytest pytest-asyncio httpx anyio

# Copy environment file
cp .env.example .env

# Run the server
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for the interactive Swagger UI.

## High-Level Architecture

```
fastapi_asyncpg_database_driver/
  app/
    main.py                     # FastAPI app factory + lifespan
    api/
      routes_products.py        # CRUD + bulk update endpoints
    core/
      config.py                 # Settings from .env
      db.py                     # asyncpg pool creation + table init
    schemas/
      product.py                # Pydantic request/response schemas
    repositories/
      product_repository.py     # Raw SQL queries (asyncpg pool calls)
    services/
      product_service.py        # Business logic layer
  migrations/
    001_create_products_table.sql   # SQL migration with indexes
  tests/
    conftest.py                 # Test fixtures (pool + table setup)
    test_products.py            # Integration tests
  docker-compose.yml            # PostgreSQL container
  pyproject.toml
  .env.example
```

Each layer has a single responsibility:

- **Routes** receive HTTP requests, validate input via Pydantic schemas, and return responses
- **Schemas** define request/response shapes with validation
- **Services** contain business logic and orchestrate repository calls
- **Repositories** execute raw SQL through `asyncpg` — no ORM abstraction
- **Core** holds configuration and database pool lifecycle

```mermaid
flowchart TD
    Client[Client] --> Router[FastAPI Router]
    Router --> Service[Product Service]
    Service --> Repository[Repository Layer]
    Repository --> Pool[asyncpg Connection Pool]
    Pool --> Postgres[(PostgreSQL)]
```

## What Are Database Drivers?

A **database driver** is a library that translates your Python code into the wire protocol a database server understands. When you write `await conn.execute("SELECT * FROM products")`, the driver:

1. Parses the SQL text
2. Encodes it in the database's wire format (binary or text)
3. Sends it over TCP to the database server
4. Receives the response
5. Decodes it into Python objects

Common Python database drivers:

| Driver | Database | Protocol | Async |
|--------|----------|----------|-------|
| `psycopg2` | PostgreSQL | Text | No |
| `asyncpg` | PostgreSQL | Binary | Yes |
| `aiosqlite` | SQLite | File | Yes |
| `aiomysql` | MySQL | Text | Yes |
| `SQLAlchemy` | Multiple | Depends on driver | Depends |

The driver sits at the bottom of the stack. ORMs like SQLAlchemy, Tortoise ORM, and SQLModel all delegate to a driver for actual communication.

## Why asyncpg Is Fast

`asyncpg` is significantly faster than alternatives like `psycopg2` or `psycopg3` for several reasons:

### 1. Binary Protocol

Most PostgreSQL drivers use the **text protocol** — they send queries as text strings and receive results as text strings, then convert them to Python types. `asyncpg` uses PostgreSQL's **binary protocol**, which transmits data in native binary format:

```
Text protocol:  int "42"  -> text "42" -> Python int 42  (encode + parse)
Binary protocol: int 42   -> binary 0x2A -> Python int 42 (zero-copy decode)
```

This eliminates string parsing overhead for numbers, dates, and other types.

### 2. Prepared Statements

`asyncpg` automatically uses PostgreSQL prepared statements. When you run the same query multiple times with different parameters:

```python
await pool.fetch("SELECT * FROM products WHERE id = $1", product_id)
```

The first call prepares the query plan on the server. Subsequent calls skip parsing and planning — they just bind new parameters. This is faster than re-parsing SQL every time.

### 3. Zero-Copy Decoding

`asyncpg` decodes binary data directly into Python objects without intermediate string representations. A PostgreSQL `INTEGER` column comes over the wire as 4 bytes and becomes a Python `int` with minimal conversion.

### 4. Pure Async

Unlike drivers that wrap synchronous C libraries with thread pools, `asyncpg` is written as a native async library from the ground up. It never blocks the event loop.

### Benchmark context

The MagicStack team (asyncpg's creators) measured asyncpg at roughly **3-5x faster than psycopg2** for equivalent operations. The gap widens with concurrent connections because asyncpg never blocks the event loop.

## Connection Pooling

### The Problem

Creating a new PostgreSQL connection for every request is expensive. Each connection requires:

1. TCP handshake (3-way)
2. TLS negotiation (if used)
3. PostgreSQL authentication
4. Session setup (encoding, timezone, etc.)

This can take **10-50ms per connection**. Under high load, this overhead dominates.

### The Solution: Connection Pool

A connection pool maintains a set of reusable connections:

```
Pool (min_size=2, max_size=10)
  ┌─────────────────────┐
  │  Connection 1 (idle) │──> Request A acquires it
  │  Connection 2 (idle) │──> Request B acquires it
  │  Connection 3 (created on demand if needed)
  │  ...up to 10 total   │
  └─────────────────────┘
```

When a request needs a database connection:
1. It calls `pool.acquire()` — gets an idle connection instantly (0ms setup)
2. Executes queries
3. Calls `pool.release()` — returns the connection to the pool

In `asyncpg`, `pool.fetch()`, `pool.execute()`, etc. handle acquire/release automatically:

```python
# These acquire a connection, run the query, and release it back
rows = await pool.fetch("SELECT * FROM products")
row = await pool.fetchrow("SELECT * FROM products WHERE id = $1", 1)

# For transactions, you need a dedicated connection
async with pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute("UPDATE products SET stock_quantity = $1 WHERE id = $2", 50, 1)
        await conn.execute("INSERT INTO audit_log (...) VALUES (...)")
```

### Pool Configuration

```python
pool = await asyncpg.create_pool(
    dsn="postgres://user:pass@localhost/db",
    min_size=2,   # Connections created on startup
    max_size=10,  # Maximum connections when under load
)
```

- `min_size`: Connections kept alive even when idle (warm pool)
- `max_size`: Upper limit — requests beyond this wait for a connection

## Raw SQL vs ORM

### Raw SQL (asyncpg)

```python
row = await pool.fetchrow(
    "INSERT INTO products (name, price) VALUES ($1, $2) RETURNING *",
    "Widget", Decimal("19.99"),
)
```

**Pros:**
- Full control over exact SQL executed
- No hidden queries or N+1 problems
- Maximum performance (no ORM overhead)
- Direct access to PostgreSQL features (RETURNING, CTEs, window functions)
- Easier to debug — you see exactly what runs

**Cons:**
- More boilerplate for simple CRUD
- You write SQL yourself (also a pro)
- Schema changes require manual SQL updates
- No type-safety between Python and SQL columns

### ORM (Tortoise ORM, SQLModel, SQLAlchemy)

```python
product = await Product.create(name="Widget", price=Decimal("19.99"))
```

**Pros:**
- Less boilerplate for simple CRUD
- Auto-generated migrations (with Aerich, Alembic)
- Type-safe model definitions
- Finder methods like `Product.filter(name__icontains="widget")`

**Cons:**
- ORM overhead (Python object construction, query building)
- Hidden queries can cause N+1 problems
- Complex queries fall back to raw SQL anyway
- Learning the ORM's query API is another layer

### When to Use Raw SQL

- High-performance APIs where every millisecond matters
- Complex queries that ORMs can't express well
- Lightweight services where ORM overhead is unnecessary
- Learning what actually happens beneath ORMs

### When to Use an ORM

- Rapid prototyping and CRUD-heavy APIs
- Teams that prefer Python objects over SQL strings
- Projects needing database-agnostic code
- When migration tooling (Aerich, Alembic) is valuable

## The Repository Pattern

The repository pattern isolates data access logic from business logic:

```
Route (HTTP) → Service (business rules) → Repository (SQL queries) → Database
```

Without the repository pattern, SQL ends up scattered in route handlers:

```python
# BAD: SQL mixed into route logic
@router.get("/products/{product_id}")
async def get_product(product_id: int):
    row = await pool.fetchrow("SELECT * FROM products WHERE id = $1", product_id)
    if not row:
        raise HTTPException(404)
    return dict(row)
```

With the repository pattern:

```python
# GOOD: clean separation
# routes_products.py
@router.get("/products/{product_id}")
async def get_product(product_id: int):
    product = await product_service.get_product_service(product_id)
    if product is None:
        raise HTTPException(404)
    return product

# product_repository.py
async def get_product_by_id(product_id: int) -> dict | None:
    row = await pool.fetchrow(
        "SELECT * FROM products WHERE id = $1", product_id,
    )
    return dict(row) if row else None
```

Benefits:
- **Testability**: Mock the repository in service tests
- **Swappability**: Replace asyncpg with another driver without touching routes or services
- **Clarity**: All SQL lives in one place
- **Encapsulation**: Services never see `asyncpg.Record` objects

## FastAPI Startup/Shutdown and DB Pools

FastAPI uses a **lifespan** context manager to initialize and tear down resources that live for the entire app lifecycle:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: create pool and initialize tables
    await connect_db()
    yield  # App is running, serving requests
    # Shutdown: close pool
    await close_db()
```

### What happens on startup

```
1. FastAPI calls connect_db()
2. asyncpg.create_pool() creates min_size connections to PostgreSQL
3. CREATE TABLE IF NOT EXISTS runs to ensure schema exists
4. Pool is stored as a module-level variable
5. App starts accepting requests
```

### What happens on shutdown

```
1. FastAPI calls close_db()
2. pool.close() gracefully closes all connections
3. Pool reference is set to None
4. App stops
```

This pattern ensures:
- Connections are ready **before** the first request arrives
- Connections are closed **after** the last request finishes
- No connection leaks between restarts

### Why not create a pool per request?

Connection pools are expensive to create. A single pool shared across all requests is the correct pattern. Each request borrows a connection from the pool via `pool.acquire()` and returns it when done.

## How `databases` Differs from `asyncpg` Directly

The [`databases`](https://github.com/encode/databases) library by Encode (the same team behind Starlette and HTTPX) provides a higher-level async database interface. It wraps asyncpg (for PostgreSQL) and aiomysql (for MySQL).

### `databases` example

```python
from databases import Database

database = Database("postgres://user:pass@localhost/db")

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# Query using databases
rows = await database.fetch_all("SELECT * FROM products WHERE price > :price", {"price": 10})
```

### Direct `asyncpg` example (this project)

```python
pool = await asyncpg.create_pool("postgres://user:pass@localhost/db")

# Query using asyncpg
rows = await pool.fetch("SELECT * FROM products WHERE price > $1", 10)
```

### Key differences

| Feature | `asyncpg` direct | `databases` |
|---------|-----------------|-------------|
| **Driver** | PostgreSQL only | PostgreSQL + MySQL + SQLite |
| **Return type** | `asyncpg.Record` (tuple-like) | `dict`-like mapping |
| **Parameter style** | Positional `$1, $2` | Named `:name` or positional `?` |
| **Connection pool** | Built-in (`create_pool`) | Built-in (wraps asyncpg's pool) |
| **Performance** | Maximum (native binary protocol) | Slightly slower (wrapping layer) |
| **Transaction API** | `async with conn.transaction()` | `async with database.transaction()` |
| **Column access** | `row["name"]` or `row[0]` | `row["name"]` |
| **Auto-mapping to dicts** | Manual (`dict(row)`) | Automatic |
| **Dependencies** | `asyncpg` only | `asyncpg` + `databases` + `sqlalchemy` core |

### When to use `databases`

- You want automatic dict-like results
- You might switch between PostgreSQL and MySQL
- You prefer named parameters (`:price`) over positional (`$1`)
- You're building a simple API and don't need maximum performance

### When to use `asyncpg` directly (this project)

- You need maximum performance
- You're using PostgreSQL-specific features (RETURNING, CTEs, JSONB)
- You want to understand what ORMs abstract away
- You want fewer dependencies

## Transactions with asyncpg

Transactions ensure multiple operations succeed or fail as a unit. With asyncpg, you use `pool.acquire()` to get a dedicated connection and `conn.transaction()` to wrap operations:

```python
async def bulk_update_stock(updates: list[tuple[int, int]]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for product_id, new_stock in updates:
                await conn.execute(
                    "UPDATE products SET stock_quantity = $1 WHERE id = $2",
                    new_stock, product_id,
                )
```

If any update fails, the `async with conn.transaction()` block automatically rolls back **all** changes. This is critical for operations like:
- Transferring stock between products (debit one, credit another)
- Order processing (reserve stock, create order, update inventory)
- Bulk imports where partial failures should not leave data inconsistent

### Nested transactions (savepoints)

```python
async with pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute("UPDATE products SET stock_quantity = 0 WHERE id = $1", 1)
        async with conn.transaction():  # Creates a SAVEPOINT
            await conn.execute("UPDATE products SET price = 0 WHERE id = $1", 2)
            # If this raises, only the inner transaction rolls back
```

## Indexes Explained

The migration file includes two indexes:

```sql
CREATE INDEX idx_products_name ON products (name);
CREATE INDEX idx_products_created_at ON products (created_at);
```

### What indexes do

An index is a sorted data structure (B-tree by default in PostgreSQL) that lets the database find rows without scanning the entire table.

**Without index on `name`:**
```
Query: SELECT * FROM products WHERE name = 'Widget'
Plan:  Sequential Scan (reads every row, checks name)
Cost:  O(n) where n = total rows
```

**With index on `name`:**
```
Query: SELECT * FROM products WHERE name = 'Widget'
Plan:  Index Scan (uses B-tree to find matching rows)
Cost:  O(log n)
```

### When to add indexes

- Columns frequently used in `WHERE` clauses
- Columns used in `ORDER BY` (the `created_at` index helps `ORDER BY created_at DESC`)
- Columns used in `JOIN` conditions
- Avoid over-indexing — each index slows writes (INSERT, UPDATE, DELETE)

## API Reference

| Method | Endpoint | Description | Request Body | Status |
|--------|----------|-------------|-------------|--------|
| `POST` | `/api/v1/products/` | Create a product | `ProductCreate` | 201 |
| `GET` | `/api/v1/products/` | List all products | - | 200 |
| `GET` | `/api/v1/products/{id}` | Get product by ID | - | 200 |
| `PATCH` | `/api/v1/products/{id}` | Update a product | `ProductUpdate` | 200 |
| `DELETE` | `/api/v1/products/{id}` | Delete a product | - | 204 |
| `POST` | `/api/v1/products/bulk-stock-update` | Bulk update stock | `BulkStockUpdate` | 204 |

### ProductCreate

```json
{
  "name": "Widget",
  "description": "A useful widget",
  "price": "19.99",
  "stock_quantity": 100
}
```

- `name`: required, 1-200 characters
- `description`: optional, defaults to empty string
- `price`: required, must be > 0
- `stock_quantity`: optional, defaults to 0, must be >= 0

### ProductUpdate (partial)

All fields optional — only provided fields are updated:

```json
{
  "stock_quantity": 50
}
```

## Code Walkthrough

### db.py — Pool Lifecycle

```python
pool: asyncpg.Pool | None = None

async def connect_db() -> None:
    global pool
    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)

async def close_db() -> None:
    global pool
    if pool:
        await pool.close()
        pool = None
```

The pool is a module-level global. `connect_db()` creates it on startup, `close_db()` destroys it on shutdown. This is the simplest pattern — in larger apps, you might use FastAPI's dependency injection instead.

### product_repository.py — Raw SQL

```python
async def create_product(name, description, price, stock_quantity) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO products (name, description, price, stock_quantity)
        VALUES ($1, $2, $3, $4)
        RETURNING id, name, description, price, stock_quantity, created_at, updated_at
        """,
        name, description, price, stock_quantity,
    )
    return dict(row)
```

Key patterns:
- `$1, $2, $3, $4` — asyncpg uses **positional parameters** (not `%s` or `?`)
- `RETURNING *` — PostgreSQL-specific, returns the inserted row without a separate SELECT
- `dict(row)` — converts `asyncpg.Record` to a plain dict for the service layer
- `pool.fetchrow()` — acquires a connection, runs the query, releases the connection

### product_service.py — Business Logic

```python
async def update_product_service(product_id: int, product_data: ProductUpdate) -> ProductResponse | None:
    update_fields = product_data.model_dump(exclude_unset=True)
    if not update_fields:
        return await get_product_service(product_id)
    ...
```

`model_dump(exclude_unset=True)` ensures partial updates only send changed fields. If the client sends `{"stock_quantity": 50}`, only `stock_quantity` is updated — `name`, `description`, and `price` are preserved.

## Testing

Tests require a running PostgreSQL instance:

```bash
# Start PostgreSQL
docker compose up -d

# Copy environment file
cp .env.example .env

# Run tests
pytest -v
```

### Test coverage

| Test | What it validates |
|------|-------------------|
| `test_create_product` | POST creates and returns product |
| `test_create_product_defaults` | POST uses default description and stock |
| `test_create_product_missing_name` | POST 422 without name |
| `test_create_product_negative_price` | POST 422 with negative price |
| `test_create_product_zero_price` | POST 422 with zero price |
| `test_create_product_negative_stock` | POST 422 with negative stock |
| `test_create_product_empty_name` | POST 422 with empty name |
| `test_list_products` | GET returns list with count |
| `test_list_products_empty` | GET works with no products |
| `test_get_product` | GET by ID returns product |
| `test_get_product_not_found` | GET returns 404 |
| `test_update_product` | PATCH changes name and price |
| `test_update_stock_quantity` | PATCH changes stock |
| `test_update_product_partial_preserves_fields` | PATCH updates only sent fields |
| `test_update_product_not_found` | PATCH returns 404 |
| `test_update_product_empty_patch` | PATCH with empty body returns product |
| `test_delete_product` | DELETE removes product |
| `test_delete_product_not_found` | DELETE returns 404 |
| `test_bulk_stock_update` | Bulk update changes multiple products |

### Test setup notes

Tests use the real PostgreSQL database (via Docker), not mocks. This ensures:
- SQL queries are validated against actual PostgreSQL
- Connection pooling works under test conditions
- Transaction behavior is correct
- `asyncpg.Record` conversion works as expected

Each test cleans up by deleting all products before and after, keeping tests isolated.

## PostgreSQL with Docker Compose

```bash
# Start PostgreSQL
docker compose up -d

# Stop PostgreSQL
docker compose down

# Stop and remove data
docker compose down -v
```

The `docker-compose.yml` includes a healthcheck so the container reports ready only when PostgreSQL is accepting connections. The migration SQL file is mounted into the container's init directory, so tables and indexes are created automatically on first start.

## Project Files at a Glance

| File | Purpose |
|------|---------|
| `app/main.py` | App factory with asyncpg pool lifespan |
| `app/core/config.py` | Pydantic Settings from env vars |
| `app/core/db.py` | Pool creation, table init, pool teardown |
| `app/schemas/product.py` | Pydantic request/response schemas |
| `app/repositories/product_repository.py` | Raw SQL queries via asyncpg |
| `app/services/product_service.py` | Business logic layer |
| `app/api/routes_products.py` | FastAPI router with 6 endpoints |
| `migrations/001_create_products_table.sql` | SQL migration with indexes |
| `tests/conftest.py` | Test fixtures with real PostgreSQL |
| `tests/test_products.py` | Integration tests |
| `docker-compose.yml` | PostgreSQL container |