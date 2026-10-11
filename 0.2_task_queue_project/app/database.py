# =====================================================================
# app/database.py - Async SQLAlchemy setup (engine, session, Base, init)
# =====================================================================
# PURPOSE
# -------
# Sets up the async SQLAlchemy stack that the API routes and the ARQ
# worker share. Provides:
#   - `engine`        : the async engine talking to the configured DB
#   - `async_session` : a sessionmaker that yields AsyncSession objects
#   - `Base`          : the declarative base every ORM model inherits
#   - `get_db()`      : FastAPI dependency yielding a per-request session
#   - `init_db()`     : creates all tables at app startup (dev only)
# =====================================================================

# Async-flavoured pieces of SQLAlchemy. `async_sessionmaker` is the v2
# factory that produces AsyncSession instances; `create_async_engine`
# builds an engine compatible with await/async.
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# `DeclarativeBase` is the SQLAlchemy 2.0 typed base class for ORM
# models. Inheriting from it gives `__tablename__`, mapped columns, etc.
from sqlalchemy.orm import DeclarativeBase

# Bring in our central config singleton so we know which DATABASE_URL
# to connect to. The settings module reads env vars / .env.
from app.config import settings


# `create_async_engine` returns an AsyncEngine. echo=False disables SQL
# logging in production; flip to True for debugging.
engine = create_async_engine(settings.DATABASE_URL, echo=False)

# Build a session factory bound to the engine above. `expire_on_commit
# =False` keeps attribute access valid after commit() — important for
# FastAPI response models, where Pydantic reads fields post-commit.
async_session = async_sessionmaker(engine, expire_on_commit=False)


# Every ORM model in app/models/ inherits from this Base. SQLAlchemy
# registers the metadata (table list) on `Base.metadata`, which is what
# `init_db()` uses below to issue CREATE TABLE statements.
class Base(DeclarativeBase):
    pass


# FastAPI dependency: yields an AsyncSession, then guarantees cleanup
# when the request finishes. Usage in routes:
#     async def my_route(db: AsyncSession = Depends(get_db)): ...
async def get_db():
    # `async with` pattern: opens the session, yields it, and on exit
    # rolls back/closes it automatically.
    async with async_session() as session:
        yield session


# One-shot helper that creates every table declared on Base.metadata.
# Called from FastAPI's lifespan() during startup. For real projects
# this is replaced by Alembic migrations — kept here for demo simplicity.
async def init_db():
    # `engine.begin()` opens an explicit transaction; everything inside
    # commits atomically when the block exits successfully.
    async with engine.begin() as conn:
        # `run_sync` adapts a sync function (Base.metadata.create_all)
        # to work inside an async connection — needed because most
        # DDL utilities in SQLAlchemy are sync-only.
        await conn.run_sync(Base.metadata.create_all)
