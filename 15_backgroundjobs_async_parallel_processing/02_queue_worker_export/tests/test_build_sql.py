"""Unit tests for ``app.jobs.build_export_sql``.

The query builder must:

* always SELECT the documented column list,
* emit positional ``$1, $2, …`` placeholders in the order of the args
  list (asyncpg requirement),
* skip ``None`` filters,
* end with ``ORDER BY created_at, id`` so the index in
  ``utils/order_events_schema.sql`` is used.
"""

from __future__ import annotations

from app.jobs import COLUMNS, build_export_sql


def test_no_filters_returns_full_table_scan_ordered():
    sql, args = build_export_sql({})
    assert args == []
    assert sql.startswith("SELECT ")
    for col in COLUMNS:
        assert col in sql
    assert "WHERE" not in sql
    assert sql.rstrip().endswith("ORDER BY created_at, id")


def test_status_only_filter():
    sql, args = build_export_sql({"status": "paid"})
    assert args == ["paid"]
    assert "WHERE status = $1" in sql
    assert sql.rstrip().endswith("ORDER BY created_at, id")


def test_multiple_filters_use_positional_placeholders_in_order():
    sql, args = build_export_sql(
        {"status": "paid", "country": "US", "customer_id": 42}
    )
    assert args == ["paid", "US", 42]
    assert "status = $1" in sql
    assert "country = $2" in sql
    assert "customer_id = $3" in sql
    # joined with AND
    assert " AND " in sql.split("WHERE", 1)[1]


def test_none_values_are_skipped():
    sql, args = build_export_sql(
        {"status": "paid", "country": None, "customer_id": None}
    )
    assert args == ["paid"]
    assert "country" not in sql.split("WHERE", 1)[1]
    assert "customer_id" not in sql.split("WHERE", 1)[1]


def test_unknown_keys_are_ignored():
    """Defence in depth: only the whitelisted columns become predicates,
    so a hostile request body can't inject ``DROP TABLE`` via the key."""
    sql, args = build_export_sql({"status": "paid", "evil": "x"})
    assert args == ["paid"]
    assert "evil" not in sql
