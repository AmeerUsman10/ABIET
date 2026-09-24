import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from backend.config import settings
from backend.services.connectors import ConnectionSpec, create_engine_for
from backend.services.demo import DEMO_FILE_NAME, ensure_demo_database
from backend.services.executor import QueryExecutionError, execute_sql, stream_csv, to_csv_value, to_json_value


@pytest.fixture
def demo_engine():
    ensure_demo_database()
    return create_engine_for(ConnectionSpec(db_type="sqlite", database=DEMO_FILE_NAME))


def test_json_serialization_of_database_values():
    assert to_json_value(Decimal("12.50")) == 12.5
    assert to_json_value(Decimal("12")) == 12
    assert to_json_value(Decimal("NaN")) is None
    assert to_json_value(float("inf")) is None
    assert to_json_value(date(2026, 1, 2)) == "2026-01-02"
    assert to_json_value(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05"
    assert to_json_value(timedelta(hours=1)) == "1:00:00"
    assert to_json_value(b"\x00\x01") == "<binary 2 bytes>"
    u = uuid.uuid4()
    assert to_json_value(u) == str(u)
    assert to_json_value([Decimal("1.5"), {"a": date(2026, 1, 1)}]) == [1.5, {"a": "2026-01-01"}]
    assert to_csv_value(None) == ""
    assert to_csv_value(["a", 1]) == '["a", 1]'


def test_results_columns_and_rows(demo_engine):
    result = execute_sql(
        demo_engine,
        "sqlite",
        "SELECT name, COUNT(*) AS n FROM regions WHERE name LIKE '%a%' GROUP BY name ORDER BY name",
        max_rows=100,
    )
    assert result.columns == ["name", "n"]
    assert result.rows and all(len(r) == 2 for r in result.rows)
    assert not result.truncated
    assert result.row_count == len(result.rows)


def test_results_are_capped(demo_engine):
    result = execute_sql(demo_engine, "sqlite", "SELECT * FROM orders", max_rows=7)
    assert result.row_count == 7 and result.truncated


def test_sql_errors_are_reported(demo_engine):
    with pytest.raises(QueryExecutionError) as info:
        execute_sql(demo_engine, "sqlite", "SELECT no_such_column FROM orders", max_rows=5)
    assert "no such column" in info.value.message
    assert not info.value.connection_error


def test_connection_errors_are_flagged():
    engine = create_engine_for(ConnectionSpec(db_type="postgresql", host="127.0.0.1", port=1, database="x"))
    with pytest.raises(QueryExecutionError) as info:
        execute_sql(engine, "postgresql", "SELECT 1", max_rows=1)
    assert info.value.connection_error


def test_long_running_queries_are_stopped(monkeypatch):
    monkeypatch.setattr(settings, "QUERY_TIMEOUT_SECONDS", 1)
    ensure_demo_database()
    engine = create_engine_for(ConnectionSpec(db_type="sqlite", database=DEMO_FILE_NAME))
    started = time.monotonic()
    with pytest.raises(QueryExecutionError, match="longer than 1 seconds"):
        execute_sql(
            engine,
            "sqlite",
            "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT COUNT(*) FROM r",
            max_rows=1,
        )
    assert time.monotonic() - started < 10
    assert execute_sql(engine, "sqlite", "SELECT 1", max_rows=1).rows == [[1]]


def test_csv_streaming(demo_engine):
    text = "".join(stream_csv(demo_engine, "sqlite", "SELECT region_id, name FROM regions ORDER BY 1", max_rows=3))
    lines = text.strip().splitlines()
    assert lines[0] == "region_id,name"
    assert len(lines) == 4


def test_csv_streaming_with_no_rows(demo_engine):
    text = "".join(stream_csv(demo_engine, "sqlite", "SELECT name FROM regions WHERE 1 = 0", max_rows=3))
    assert text.strip() == "name"
