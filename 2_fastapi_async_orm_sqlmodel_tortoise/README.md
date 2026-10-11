# FastAPI Async ORM: Tortoise ORM & SQLModel

A tutorial-friendly Task Manager API that teaches async database interaction in FastAPI using ORM patterns. The main implementation uses **Tortoise ORM**, with a runnable **SQLModel** alternative included for comparison.

## What You'll Learn

- How async ORMs work with FastAPI's event loop
- CRUD operations with Tortoise ORM
- Layered architecture: routes, schemas, services, models
- Why async database calls matter for FastAPI performance
- How Tortoise ORM and SQLModel compare

## Quick Start

```bash
# Initialize project
uv init

# Create and activate virtual environment
uv venv fastapi_async_orm_env
source fastapi_async_orm_env/bin/activate

# Install dependencies
uv pip install fastapi uvicorn tortoise-orm aiosqlite pydantic-settings pytest pytest-asyncio httpx anyio

# Run the Tortoise ORM version
uvicorn app.main:app --reload

# Run the SQLModel version (alternative)
uvicorn app_sqlmodel.main:app --port 8001 --reload
```

Open `http://localhost:8000/docs` for the interactive Swagger UI.

## High-Level Architecture

```
fastapi_async_orm_sqlmodel_tortoise/
  app/                          # Main implementation (Tortoise ORM)
    main.py                     # FastAPI app factory + lifespan
    api/
      routes_tasks.py           # CRUD endpoints
    core/
      config.py                 # Settings from .env
      database.py               # Tortoise ORM configuration
    models/
      task.py                   # Tortoise ORM Task model
    schemas/
      task.py                   # Pydantic request/response schemas
    services/
      task_service.py           # Business logic layer
  app_sqlmodel/                 # Alternative implementation (SQLModel)
    main.py
    api/routes_tasks.py
    core/config.py, database.py
    models/task.py
    schemas/task.py
    services/task_service.py
  tests/
    conftest.py                 # Test fixtures
    test_tasks.py                # Integration tests
  docker-compose.yml            # PostgreSQL for production
  pyproject.toml
  .env.example
```

Each layer has a single responsibility:

- **Routes** receive HTTP requests, validate input via schemas, and return responses
- **Schemas** define request/response shapes with Pydantic validation
- **Services** contain business logic and ORM calls
- **Models** define database tables with Tortoise ORM (or SQLModel)
- **Core** holds configuration and database setup

## Request Lifecycle

When a client sends `POST /api/v1/tasks/` with `{"title": "Buy milk"}`:

1. **FastAPI Router** matches the URL and HTTP method to `create_task` in `routes_tasks.py`
2. **Pydantic Schema** (`TaskCreate`) validates the request body — `title` is required, `status` defaults to `"pending"`
3. **Service Layer** (`task_service.create_task`) calls `Task.create()` on the Tortoise ORM model
4. **Tortoise ORM** generates `INSERT INTO tasks (title, description, status) VALUES (?, ?, ?)` and executes it asynchronously via `aiosqlite`
5. The created `Task` instance is serialized using `TaskResponse` and returned with status `201`

```mermaid
flowchart TD
    Client[Client] --> API[FastAPI Router]
    API --> Schema[Pydantic Schemas]
    Schema --> Service[Task Service]
    Service --> ORM[Tortoise ORM]
    ORM --> DB[(SQLite Database)]
```

## ORM Lifecycle

### Tortoise ORM Init Sequence

```
App startup (lifespan)
  --> RegisterTortoise connects to DB
  --> Tortoise.generate_schemas() creates tables
  --> App is ready to serve requests

App shutdown
  --> Tortoise.close_connections() cleanup
```

### Model Definition Flow

```
1. Define Model class (Task) with fields
2. Tortoise.init_models() called early in app/__init__.py
   - Makes model metadata available for Pydantic schema generation
3. RegisterTortoise called during lifespan
   - Creates database connection
   - Generates schema (creates tables)
4. Service functions use Model.create(), Model.get(), Model.filter() etc.
   - All are awaitable (async) methods
```

## API Reference

| Method   | Endpoint              | Description          | Request Body        | Status |
|----------|-----------------------|----------------------|---------------------|--------|
| `POST`   | `/api/v1/tasks/`     | Create a new task    | `TaskCreate`        | 201    |
| `GET`    | `/api/v1/tasks/`     | List all tasks       | -                   | 200    |
| `GET`    | `/api/v1/tasks/{id}`  | Get task by ID       | -                   | 200    |
| `PATCH`  | `/api/v1/tasks/{id}`  | Update a task        | `TaskUpdate`        | 200    |
| `DELETE` | `/api/v1/tasks/{id}`  | Delete a task        | -                   | 204    |

### Task Status Values

| Status        | Meaning                    |
|---------------|----------------------------|
| `pending`     | Task created, not started  |
| `in_progress` | Task is being worked on    |
| `completed`   | Task is finished           |

## Code Walkthrough

### Model (`app/models/task.py`)

```python
class Task(Model):
    id = fields.IntField(primary_key=True)
    title = fields.CharField(max_length=200)
    description = fields.TextField(default="")
    status = fields.CharField(max_length=20, default="pending")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tasks"
```

- `IntField(primary_key=True)` — auto-incrementing ID
- `DatetimeField(auto_now_add=True)` — set once at creation
- `DatetimeField(auto_now=True)` — updated on every save

### Schema (`app/schemas/task.py`)

```python
class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    status: TaskStatus = Field(default=TaskStatus.pending)

class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: TaskStatus | None = None
```

- `TaskCreate` requires `title`, all other fields have defaults
- `TaskUpdate` makes every field optional (`None` default) for partial updates
- `TaskStatus` enum gives validation and OpenAPI docs for free

### Service (`app/services/task_service.py`)

```python
async def create_task(task_data: TaskCreate) -> Task:
    task = await Task.create(**task_data.model_dump())
    return task

async def update_task(task_id: int, task_data: TaskUpdate) -> Task | None:
    task = await Task.get_or_none(id=task_id)
    if not task:
        return None
    update_data = task_data.model_dump(exclude_unset=True)
    if update_data:
        await task.update_from_dict(update_data).save()
    return task
```

- All service functions are `async` — they await ORM calls
- `model_dump(exclude_unset=True)` ensures partial updates only send changed fields
- `get_or_none()` returns `None` instead of raising `DoesNotExist`

## Testing

```bash
pytest -v
```

Tests use `httpx.AsyncClient` with `ASGITransport` to call the FastAPI app directly — no running server needed. Each test uses the async event loop via `pytest-asyncio`.

**Test coverage:**

| Test | What it validates |
|------|-------------------|
| `test_create_task` | POST creates and returns task |
| `test_create_task_with_status` | POST accepts custom status |
| `test_create_task_missing_title` | POST 422 without title |
| `test_create_task_empty_title` | POST 422 with empty string title |
| `test_create_task_invalid_status` | POST 422 with invalid status |
| `test_list_tasks` | GET returns list with count |
| `test_list_tasks_empty` | GET works with no tasks |
| `test_get_task` | GET by ID returns task |
| `test_get_task_not_found` | GET returns 404 |
| `test_update_task_status` | PATCH changes status |
| `test_update_task_title_and_description` | PATCH changes multiple fields |
| `test_update_task_not_found` | PATCH returns 404 |
| `test_delete_task` | DELETE removes task |
| `test_delete_task_not_found` | DELETE returns 404 |
| `test_update_partial_only_status` | PATCH updates only status, preserves other fields |

---

## Tortoise ORM vs SQLModel

| Feature | Tortoise ORM | SQLModel |
|---------|-------------|----------|
| **Async support** | Native async (built-in) | Async via SQLAlchemy async engine |
| **Underlying engine** | Own query builder | SQLAlchemy + Pydantic |
| **Model definition** | `Model` subclass with `fields.*` | `SQLModel` subclass (table=True) |
| **Schema generation** | `pydantic_model_creator` or hand-written | Model IS the schema (or separate) |
| **Migrations** | Aerich (built-in tool) | Alembic |
| **Relations** | ForeignKey, ManyToMany, ReverseRelation | SQLAlchemy relationships |
| **Query API** | `Model.filter()`, `Model.get()`, `Model.all()` | SQLAlchemy `select()`, `session.exec()` |
| **Pydantic version** | Pydantic v2 compatible | Pydantic v2 compatible |
| **Documentation** | Good, focused | Growing, designed by FastAPI creator |
| **Maturity** | Mature, production-ready | Young, evolving API |
| **Best for** | Greenfield async projects | Projects wanting SQLAlchemy power |

### Key Difference in This Project

**Tortoise ORM** service (no session injection needed):
```python
async def create_task(task_data: TaskCreate) -> Task:
    task = await Task.create(**task_data.model_dump())
    return task
```

**SQLModel** service (session injected via FastAPI Depends):
```python
async def create_task(session: AsyncSession, task_data: TaskCreate) -> Task:
    task = Task(**task_data.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task
```

## Async ORM vs Sync ORM

### What happens with sync ORM in FastAPI?

FastAPI runs on a single-threaded async event loop (via uvicorn). When a route calls a **synchronous** database driver (like `sqlite3` or `psycopg2`), the entire event loop blocks:

```python
# BAD: sync DB call blocks the event loop
@app.get("/tasks/")
def list_tasks():
    tasks = Session.query(Task).all()  # BLOCKS all other requests
    return tasks
```

While this query runs, **no other request can be processed**. Under load, response times compound:

```
Request 1: waiting for DB... (50ms blocked)
Request 2: waiting for Request 1... then DB... (50ms + 50ms = 100ms)
Request 3: waiting for Request 2... (150ms)
```

### How async ORM fixes this

With an async driver (`aiosqlite`, `asyncpg`), the DB call yields control back to the event loop:

```python
# GOOD: async DB call yields to event loop
@app.get("/tasks/")
async def list_tasks():
    tasks = await Task.all()  # Other requests can proceed
    return tasks
```

During the `await`, the event loop serves other requests:

```
Request 1: await DB...switches to Request 2
Request 2: await DB...switches to Request 3
Request 3: await DB...
DB responds to all -> all requests complete faster
```

### When blocking calls are acceptable

- Scripts, management commands, or background tasks running outside the event loop
- FastAPI endpoints using `def` (not `async def`) — FastAPI runs them in a thread pool automatically

### When async is essential

- Any `async def` endpoint that touches a database
- High-concurrency APIs under load
- Real-time endpoints (WebSocket, SSE) sharing the same event loop

## When to Choose Which ORM

### Choose Tortoise ORM when:

- Starting a new async FastAPI project from scratch
- You want a clean, Django-like ORM API with native async
- You prefer explicit model definitions over SQLAlchemy complexity
- You want built-in Pydantic integration
- You don't need SQLAlchemy's full feature set

### Choose SQLModel when:

- You need SQLAlchemy's powerful query capabilities
- Your project already uses SQLAlchemy/alembic
- You want Pydantic models that are also database models (double duty)
- You want the FastAPI creator's recommended ORM
- You need to mix sync and async patterns

### Choose SQLAlchemy (raw) when:

- You need maximum control over queries
- You're migrating an existing SQLAlchemy project to async
- You want the largest ecosystem of extensions

## PostgreSQL with Docker Compose

For production or PostgreSQL testing:

```bash
# Start PostgreSQL
docker compose up -d

# Update .env
DB_URL=postgres://taskuser:taskpass@localhost:5432/taskdb

# Run with PostgreSQL
uvicorn app.main:app --reload

# Stop PostgreSQL
docker compose down
```

## Aerich Migrations

[Aerich](https://github.com/tortoise/aerich) is Tortoise ORM's migration tool, similar to Django's makemigrations.

```bash
# Install
uv pip install aerich

# Initialize (only once)
aerich init -t app.core.database.TORTOISE_ORM

# Generate first migration
aerich init-db

# After model changes, generate new migration
aerich migrate --name "description"

# Apply migrations
aerich upgrade

# Rollback last migration
aerich downgrade
```

Aerich tracks migration history in a `migrations/` directory. Each migration has `upgrade()` and `downgrade()` methods.

> **Note:** For this tutorial, `generate_schemas=True` in `RegisterTortoise` creates tables automatically. In production, use Aerich migrations instead.

## Project Files at a Glance

| File | Purpose |
|------|---------|
| `app/main.py` | App factory with Tortoise lifespan |
| `app/core/config.py` | Pydantic Settings from env vars |
| `app/core/database.py` | Tortoise config + `register_orm` |
| `app/models/task.py` | Task model with all fields |
| `app/schemas/task.py` | Pydantic request/response schemas |
| `app/services/task_service.py` | Async CRUD business logic |
| `app/api/routes_tasks.py` | FastAPI router with 5 endpoints |
| `app_sqlmodel/` | Complete SQLModel alternative |
| `tests/` | Integration tests |