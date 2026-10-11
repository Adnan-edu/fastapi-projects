"""Unit tests for the SQL builder — also test #10 (filter whitelist)."""

from app.jobs import build_export_sql


def test_filters_are_whitelisted():
    """Test 10 — junk keys are silently dropped before reaching SQL."""

    sql, args = build_export_sql({"status": "paid", "evil": "DROP TABLE x"})
    assert "evil" not in sql
    assert "DROP" not in sql
    assert args == ["paid"]


def test_no_filters_means_no_where():
    sql, args = build_export_sql({})
    assert " WHERE " not in sql
    assert args == []
    assert sql.endswith(" ORDER BY created_at, id")


def test_multi_filter_positional_args():
    sql, args = build_export_sql({"status": "paid", "country": "US"})
    # status comes first by whitelist order
    assert args == ["paid", "US"]
    assert "status = $1" in sql
    assert "country = $2" in sql
