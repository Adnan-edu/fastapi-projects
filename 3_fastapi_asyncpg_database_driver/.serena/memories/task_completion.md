# Task Completion

- Requires live Postgres: `docker compose up -d` + `cp .env.example .env` if missing before verifying
- Run: `pytest -v` (full integration suite, real DB, auto cleanup via DELETE FROM products in conftest)
- No linter/formatter/typechecker configured (no ruff/black/mypy in pyproject) — do not invent lint commands
- Manual smoke: `uvicorn app.main:app --reload` + check `http://localhost:8000/docs`
- After schema change: update BOTH `migrations/001_create_products_table.sql` and `CREATE_TABLES_SQL` in `app/core/db.py` (kept in sync manually)
