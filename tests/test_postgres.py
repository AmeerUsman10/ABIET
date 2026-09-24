"""
PostgreSQL integration tests against a real server.

Run with e.g.
    ABIET_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest tests/test_postgres.py
"""

import os
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from backend.config import settings
from backend.services.connectors import ConnectionSpec, create_engine_for, introspect_schema
from backend.services.executor import QueryExecutionError, execute_sql, stream_csv

URL = os.environ.get("ABIET_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set ABIET_TEST_POSTGRES_URL to run PostgreSQL integration tests")

SETUP = """
DROP SCHEMA IF EXISTS abiet_it CASCADE;
CREATE SCHEMA abiet_it;
CREATE TABLE abiet_it.customers (id serial PRIMARY KEY, name text NOT NULL, tier varchar(20) NOT NULL);
CREATE TABLE abiet_it.orders (
    id serial PRIMARY KEY,
    customer_id int NOT NULL REFERENCES abiet_it.customers(id),
    amount numeric(10, 2) NOT NULL,
    status varchar(20) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    meta jsonb,
    tags text[]
);
COMMENT ON COLUMN abiet_it.orders.amount IS 'Order total in USD';
CREATE VIEW abiet_it.big_orders AS SELECT * FROM abiet_it.orders WHERE amount > 1000;
INSERT INTO abiet_it.customers (name, tier)
    SELECT 'Customer ' || g, (ARRAY['gold', 'silver', 'bronze'])[1 + g % 3] FROM generate_series(1, 30) g;
INSERT INTO abiet_it.orders (customer_id, amount, status, meta, tags)
    SELECT 1 + g % 30, (g * 13.37)::numeric(10, 2), (ARRAY['paid', 'refunded', 'pending'])[1 + g % 3],
           jsonb_build_object('source', 'web'), ARRAY['a', 'b']
    FROM generate_series(1, 3000) g;
"""


@pytest.fixture(scope="module")
def spec():
    admin = create_engine(URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execution_options(no_parameters=True).exec_driver_sql(SETUP)  # SQL contains % operators
    admin.dispose()
    url = make_url(URL)
    return ConnectionSpec(
        db_type="postgresql",
        host=url.host,
        port=url.port,
        database=url.database,
        username=url.username,
        password=url.password,
        options={"schemas": "abiet_it"},
    )


@pytest.fixture
def engine(spec):
    engine = create_engine_for(spec)
    yield engine
    engine.dispose()


def test_introspection(engine, spec):
    schema = introspect_schema(engine, spec)
    tables = {t["name"]: t for t in schema["tables"]}
    assert set(tables) == {"customers", "orders", "big_orders"}
    assert tables["big_orders"]["kind"] == "view"
    assert all(t["schema"] == "abiet_it" for t in schema["tables"])
    cols = {c["name"]: c for c in tables["orders"]["columns"]}
    assert cols["tags"]["type"] == "TEXT[]"
    assert cols["amount"]["comment"] == "Order total in USD"
    assert cols["status"]["values"] == ["paid", "pending", "refunded"]
    assert {c["name"]: c for c in tables["customers"]["columns"]}["tier"]["values"] == ["bronze", "gold", "silver"]
    fk = tables["orders"]["foreign_keys"][0]
    assert fk["referred_table"] == "customers" and fk["referred_schema"] == "abiet_it"


def test_execution_handles_postgres_syntax_and_types(engine):
    result = execute_sql(
        engine,
        "postgresql",
        "SELECT c.tier, COUNT(*) AS n, SUM(o.amount) AS total, MIN(o.created_at)::date AS first_day, "
        "MAX(o.meta->>'source') AS source, (ARRAY_AGG(o.meta))[1] AS meta_any "
        "FROM abiet_it.orders o JOIN abiet_it.customers c ON c.id = o.customer_id "
        "WHERE c.name LIKE 'Customer 1%' GROUP BY c.tier ORDER BY c.tier",
        max_rows=100,
    )
    assert result.columns == ["tier", "n", "total", "first_day", "source", "meta_any"]
    row = result.rows[0]
    assert isinstance(row[1], int) and isinstance(row[2], (int, float))  # whole decimals become ints
    assert row[4] == "web" and row[5] == {"source": "web"}
    arrays = execute_sql(engine, "postgresql", "SELECT tags FROM abiet_it.orders LIMIT 1", max_rows=1)
    assert arrays.rows == [[["a", "b"]]]


def test_large_results_stream_and_truncate(engine):
    result = execute_sql(engine, "postgresql", "SELECT * FROM abiet_it.orders", max_rows=25)
    assert result.row_count == 25 and result.truncated


def test_read_only_transactions_block_side_effects(engine):
    with pytest.raises(QueryExecutionError, match="read-only transaction"):
        execute_sql(engine, "postgresql", "SELECT nextval('abiet_it.orders_id_seq')", max_rows=1, read_only=True)


def test_writes_commit_only_in_write_mode(engine):
    execute_sql(engine, "postgresql", "UPDATE abiet_it.customers SET tier = 'gold' WHERE id = 1", max_rows=1,
                read_only=False)  # fmt: skip
    rows = execute_sql(engine, "postgresql", "SELECT tier FROM abiet_it.customers WHERE id = 1", max_rows=1).rows
    assert rows == [["gold"]]


def test_statement_timeout(spec, monkeypatch):
    monkeypatch.setattr(settings, "QUERY_TIMEOUT_SECONDS", 1)
    engine = create_engine_for(spec)
    started = time.monotonic()
    with pytest.raises(QueryExecutionError, match="statement timeout"):
        execute_sql(engine, "postgresql", "SELECT COUNT(*) FROM generate_series(1, 1e10)", max_rows=1)
    assert time.monotonic() - started < 10
    engine.dispose()


def test_csv_export(engine):
    text = "".join(stream_csv(engine, "postgresql", "SELECT id, amount FROM abiet_it.orders ORDER BY id", max_rows=3))
    assert text.splitlines() == ["id,amount", "1,13.37", "2,26.74", "3,40.11"]


def test_ask_flow_against_postgres(client, auth, fake_llm, spec):
    conn = client.post(
        "/api/v1/connections",
        headers=auth,
        json={
            "name": "PG",
            "db_type": "postgresql",
            "host": spec.host,
            "port": spec.port,
            "database": spec.database,
            "username": spec.username,
            "password": spec.password,
            "options": {"schemas": "abiet_it"},
        },
    ).json()
    assert client.post(f"/api/v1/connections/{conn['id']}/test", headers=auth).json()["ok"]
    fake_llm.queue(
        {
            "sql": "SELECT status, COUNT(*) AS orders FROM abiet_it.orders GROUP BY status ORDER BY status",
            "explanation": "Orders by status.",
        }
    )
    body = client.post(
        "/api/v1/query/ask", headers=auth, json={"connection_id": conn["id"], "question": "Orders by status"}
    ).json()
    assert body["query"]["status"] == "success"
    assert body["result"]["rows"] == [["paid", 1000], ["pending", 1000], ["refunded", 1000]]
    prompt = fake_llm.last_system_prompt
    assert "PostgreSQL" in prompt and "TABLE abiet_it.orders" in prompt
    assert "-> abiet_it.customers.id" in prompt
