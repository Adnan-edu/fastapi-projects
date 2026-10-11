# Suggested Commands

- DB start: `docker compose up -d` (project root); stop: `docker compose down`; wipe data: `docker compose down -v`
- Env: `cp .env.example .env` (required before run/test)
- Install (uv): `uv venv fastapi_asyncpg_env && source fastapi_asyncpg_env/bin/activate && uv pip install fastapi "uvicorn[standard]" asyncpg pydantic-settings pytest pytest-asyncio httpx anyio` — or `uv pip install -e ".[dev]"`
- Run: `uvicorn app.main:app --reload` → docs at `http://localhost:8000/docs`
- Test: `pytest -v` (requires DB up + `.env`); single file: `pytest tests/test_products.py -v`
- Darwin note: `source fastapi_asyncpg_env/bin/activate` path is zsh-compatible; no GNU-specific flags used in project commands
