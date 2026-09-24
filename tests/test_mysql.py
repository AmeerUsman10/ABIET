"""
MySQL / MariaDB integration tests against a real server.

Run with e.g.
    ABIET_TEST_MYSQL_URL=mysql+pymysql://root:mysql@127.0.0.1:3306/abiet_it pytest tests/test_mysql.py
The database must exist; the user needs permission to create tables in it.
"""

import os
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from backend.config import settings
from backend.services.connectors import ConnectionSpec, create_engine_for, introspect_schema
from backend.services.executor import QueryExecutionError, execute_sql, stream_csv

URL = os.environ.get("ABIET_TEST_MYSQL_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set ABIET_TEST_MYSQL_URL to run MySQL integration tests")

SETUP = [
    "DROP TABLE IF EXISTS orders",
    "DROP TABLE IF EXISTS customers",
    "DROP TABLE IF EXISTS digits",
    "CREATE TABLE customers (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) NOT NULL, tier VARCHAR(20) NOT NULL)",
    "CREATE TABLE orders (id INT AUTO_INCREMENT PRIMARY KEY, customer_id INT NOT NULL, amount DECIMAL(10, 2) NOT NULL,"
    " status VARCHAR(20) NOT NULL, meta JSON, FOREIGN KEY (customer_id) REFERENCES customers(id))",
    "CREATE TABLE digits (d INT PRIMARY KEY)",
    "INSERT INTO digits VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9)",
    "INSERT INTO customers (name, tier) SELECT CONCAT('Customer ', a.d * 10 + b.d + 1), ELT(1 + (a.d * 10 + b.d) % 3,"
    " 'gold', 'silver', 'bronze') FROM digits a CROSS JOIN digits b WHERE a.d < 3",
    # 100,000 orders
    "INSERT INTO orders (customer_id, amount, status, meta)"
    " SELECT 1 + n % 30, (n + 1) * 1.25, ELT(1 + n % 3, 'paid', 'refunded', 'pending'), JSON_OBJECT('source', 'web')"
    " FROM (SELECT a.d + 10 * b.d + 100 * c.d + 1000 * e.d + 10000 * f.d AS n"
    " FROM digits a, digits b, digits c, digits e, digits f) t ORDER BY n",
]


@pytest.fixture(scope="module")
def spec():
    admin = create_engine(URL)
    with admin.begin() as conn:
        for statement in SETUP:
            conn.execution_options(no_parameters=True).exec_driver_sql(statement)
    admin.dispose()
    url = make_url(URL)
    return ConnectionSpec(
        db_type="mysql",
        host=url.host,
        port=url.port,
        database=url.database,
        username=url.username,
        password=url.password,
    )


@pytest.fixture
def engine(spec):
    engine = create_engine_for(spec)
    yield engine
    engine.dispose()


def test_introspection(engine, spec):
    schema = introspect_schema(engine, spec)
    tables = {t["name"]: t for t in schema["tables"]}
    assert {"customers", "orders"} <= set(tables)
    cols = {c["name"]: c for c in tables["orders"]["columns"]}
    assert cols["status"]["values"] == ["paid", "pending", "refunded"]
    assert tables["orders"]["foreign_keys"][0]["referred_table"] == "customers"


def test_execution_with_mysql_syntax(engine):
    result = execute_sql(
        engine,
        "mysql",
        "SELECT c.tier, COUNT(*) AS n, SUM(o.amount) AS total,"
        " MAX(JSON_UNQUOTE(JSON_EXTRACT(o.meta, '$.source'))) AS src"
        " FROM orders o JOIN customers c ON c.id = o.customer_id WHERE c.name LIKE 'Customer 1%'"
        " GROUP BY c.tier ORDER BY c.tier",
        max_rows=10,
    )
    assert result.columns == ["tier", "n", "total", "src"]
    assert result.rows and result.rows[0][3] == "web"


def test_truncated_results_do_not_read_the_whole_table(engine):
    started = time.monotonic()
    result = execute_sql(engine, "mysql", "SELECT * FROM orders", max_rows=5)
    assert result.row_count == 5 and result.truncated
    assert time.monotonic() - started < 2
    assert execute_sql(engine, "mysql", "SELECT 1 AS ok", max_rows=1).rows == [[1]]  # the pool recovers


def test_read_only_transactions(engine):
    with pytest.raises(QueryExecutionError, match="READ ONLY"):
        execute_sql(engine, "mysql", "UPDATE customers SET tier = 'gold' WHERE id = 1", max_rows=1, read_only=True)
    result = execute_sql(
        engine, "mysql", "UPDATE customers SET tier = 'gold' WHERE id = 1", max_rows=1, read_only=False
    )
    assert result.affected_rows in (0, 1)


def test_statement_timeout(spec, monkeypatch):
    monkeypatch.setattr(settings, "QUERY_TIMEOUT_SECONDS", 1)
    engine = create_engine_for(spec)
    started = time.monotonic()
    with pytest.raises(QueryExecutionError, match="longer than 1 seconds"):
        execute_sql(engine, "mysql", "SELECT SUM(a.amount * b.amount) FROM orders a CROSS JOIN orders b", max_rows=1)
    assert time.monotonic() - started < 10
    assert execute_sql(engine, "mysql", "SELECT 1 AS ok", max_rows=1).rows == [[1]]
    engine.dispose()


def test_csv_export_stops_early(engine):
    started = time.monotonic()
    text = "".join(stream_csv(engine, "mysql", "SELECT id, amount FROM orders ORDER BY id", max_rows=3))
    lines = text.splitlines()
    assert lines[0] == "id,amount"
    assert [line.split(",")[0] for line in lines[1:]] == ["1", "2", "3"]
    assert time.monotonic() - started < 2
