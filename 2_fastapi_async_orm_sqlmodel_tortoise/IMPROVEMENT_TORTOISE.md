# IMPROVEMENT_TORTOISE — Suggested Changes (no code changed)

> Review of `2_fastapi_async_orm_sqlmodel_tortoise` (Tortoise `app/` + SQLModel `app_sqlmodel/`).
> Status: suggestions only. Nothing applied.
> Priority: P0 = correctness, P1 = prod-readiness, P2 = testing/structure, P3 = nit.

---

## P0 — Correctness / small bugs

### 1. `title="   "` passes validation — `app/schemas/task.py:13`, `app_sqlmodel/schemas/task.py:13`
**Problem:** `Field(min_length=1)` counts whitespace, so blank titles are stored.
**Suggestion:**
```python
# before
title: str = Field(..., min_length=1, max_length=200)
# after
title: str = Field(..., min_length=1, max_length=200, strip_whitespace=True)
# + add a model_validator to reject "" after strip if on Pydantic <2.11 behavior
```

### 2. `TaskResponse.status: str` loses the enum — `app/schemas/task.py:25-33`, `app_sqlmodel/schemas/task.py:25-33`
**Problem:** Input validates via `TaskStatus`, output docs/validation fall back to free `str`.
**Suggestion:**
```python
# before
status: str
# after
status: TaskStatus
```

### 3. No DB-level status constraint — `app/models/task.py:8`, `app_sqlmodel/models/task.py:12`
**Problem:** `CharField(max_length=20)` / `str` column accepts anything via raw SQL, Aerich, or shell.
**Suggestion:**
```python
# Tortoise
status = fields.CharField(max_length=20, default="pending",
    choices=["pending", "in_progress", "completed"])
# SQLModel
import sqlalchemy as sa
status: TaskStatus = Field(default=TaskStatus.pending,
    sa_column=sa.Column(sa.Enum(TaskStatus, name="taskstatus")))
```

### 4. Timezone drift — `app/models/task.py:10-11` vs `app_sqlmodel/models/task.py:13-16`
**Problem:** Tortoise `auto_now_add/auto_now` → naive datetime; SQLModel `datetime.now(timezone.utc)` → aware. Mixed serialization + Postgres `timestamptz` comparison bugs.
**Suggestion:** Standardize on aware UTC everywhere; set Postgres columns to `timestamptz`; add a test asserting `created_at.tzinfo is not None`.

---

## P1 — Prod-readiness (fix before deploy)

### 5. Unbounded list endpoint — `app/api/routes_tasks.py:15-18`, `app_sqlmodel/api/routes_tasks.py:17-20`
**Problem:** `await Task.all()` / `select(Task)` with no `LIMIT`. First 100k-row table = OOM + p99 spike.
**Suggestion:**
```python
from fastapi import Query
@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: TaskStatus | None = None,
):
    qs = Task.all().order_by("-created_at").limit(limit).offset(offset)
    if status:
        qs = qs.filter(status=status.value)
    tasks = await qs
    return TaskListResponse(tasks=tasks, count=len(tasks))
# SQLModel mirror: select(Task).where(...).order_by(...).limit(limit).offset(offset)
# Follow-up: return total count via separate COUNT(*) for real pagination.
```

### 6. `generate_schemas=True` hardcoded — `app/core/database.py:21-25`
**Problem:** Tutorial default auto-creates tables; in prod it hides migrations and risks schema drift.
**Suggestion:**
```python
# add to Settings: env: str = "dev"
register_orm = partial(RegisterTortoise, config=TORTOISE_ORM,
    generate_schemas=(settings.env == "dev"))
# prod path: aerich migrate / aerich upgrade in CI; same for SQLModel: Alembic, not create_all.
```

### 7. Missing `GET /health` — `app/main.py`, `app_sqlmodel/main.py`
**Problem:** No cheap probe for Docker/K8s; inconsistent with sibling projects (`1_*`, `0.*`).
**Suggestion:** Add dependency-free `GET /health → {"status":"ok"}` + separate `GET /ready` that checks DB.

### 8. Single `DB_URL` can't serve both ORMs — `app/core/config.py:6`, `app_sqlmodel/core/config.py:6`, `.env.example:2`
**Problem:** Tortoise wants `sqlite://...` / `postgres://...`; SQLAlchemy needs `sqlite+aiosqlite:///...` / `postgresql+asyncpg://...`. Setting one breaks the other.
**Suggestion:** Split env vars (`DB_URL_TORTOISE`, `DB_URL_SQLMODEL`) or add a translator:
```python
def to_sqlalchemy_url(url: str) -> str:
    return url.replace("postgres://", "postgresql+asyncpg://").replace("sqlite://", "sqlite+aiosqlite:///")
```

### 9. Unvalidated `task_id` — `app/api/routes_tasks.py:22,30,38`
**Problem:** `GET /tasks/0` / `-5` hits DB pointlessly.
**Suggestion:**
```python
from fastapi import Path
async def get_task(task_id: int = Path(gt=0)): ...
```

---

## P2 — Testing / structure

### 10. Import-time side effect — `app/__init__.py:1-3`
**Problem:** `Tortoise.init_models([...])` on import pollutes global registry; breaks if `app` + `app_sqlmodel` are imported in one process; `RegisterTortoise` already handles it.
**Suggestion:** Delete the file content (leave empty `__init__.py`) or move into an explicit `init_orm_metadata()` called from lifespan.

### 11. Tests bypass lifespan — `tests/conftest.py:23-35`, `app/main.py:13-15`
**Problem:** `setup_db` calls `Tortoise.init()` manually; `ASGITransport(app)` never runs `lifespan` (`register_orm`). Startup/shutdown path is untested; double-init risk if lifespan ever fires.
**Suggestion:** Use `asgi-lifespan`:
```python
from asgi_lifespan import LifespanManager
async with LifespanManager(app):  # with TEST_DB_URL patched via monkeypatch
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
```

### 12. Private API `Tortoise._drop_databases()` — `tests/conftest.py:34`
**Problem:** Underscore API breaks on minor version bumps.
**Suggestion:** Pin `tortoise-orm>=0.23,<0.24` or wrap + fallback to `connections.close_all()`.

### 13. `app_sqlmodel` has zero tests
**Problem:** 15 tests cover Tortoise only; SQLModel drift goes undetected.
**Suggestion:** Parametrize suite or duplicate with `app.dependency_overrides[get_session]` → temp file SQLite (not `:memory:`, which breaks with pooled async connections).

### 14. Redundant `@pytest.mark.asyncio` — `tests/test_tasks.py`, `pyproject.toml:32-34`
**Problem:** `asyncio_mode="auto"` already makes every test async.
**Suggestion:** Remove decorators, or switch to `asyncio_mode="strict"` and keep them. Pick one.

---

## P3 — Nits / consistency notes

- **15. Lost-update race:** `app/services/task_service.py:18-25` (`get` + `save`), same in SQLModel `update_task`. Fine for tutorial; note `in_transaction()` / `SELECT FOR UPDATE` for real concurrent PATCH.
- **16. Delete asymmetry:** Tortoise `filter(id=...).delete()` (1 query) vs SQLModel `get` + `delete` (2 queries). Intentional tradeoff — document it in README comparison.
- **17. Dead handler:** `tortoise_exception_handlers()` in `app/main.py:24` never fires (code uses `get_or_none`, not `get`). Either use `Task.get()` + let handlers map `DoesNotExist→404`, or drop the import.
- **18. Cwd-relative `.env`:** `model_config={"env_file":".env"}` resolves from cwd, so running from repo root vs project dir loads different files. Use absolute path or `env_prefix`.
- **19. DELETE 204 style:** `delete_task` returns implicit `None` — correct for 204, but add explicit `return None` for linters; consider `Response(status_code=204)`.

---

## Suggested order
1. P0 items 1–4 (30 min, all safe).
2. P1 items 5 (pagination), 8 (URL split), 7 (health) before any deploy.
3. P2 items 11 + 13 when touching tests next.
4. P1 item 6 (Aerich gating) at first Postgres staging deploy.
