import pytest
from sqlalchemy import create_engine

from backend.config import settings
from backend.services.connectors import (
    ConnectionSpec,
    ConnectorError,
    build_url,
    create_engine_for,
    describe_error,
    introspect_schema,
    resolve_sqlite_path,
)
from backend.services.connectors import test_connection as check_connection
from backend.services.demo import DEMO_FILE_NAME, ensure_demo_database


def connect_args(url):
    engine = create_engine(url)
    return engine.dialect.create_connect_args(engine.url)


def test_mssql_named_instance_and_special_character_password():
    spec = ConnectionSpec(
        db_type="mssql",
        host="localhost",
        port=1433,
        database="Sales",
        username="sa",
        password="p@ss:w/rd;{x}",
        options={"instance": "SQLEXPRESS"},
    )
    url = build_url(spec)
    assert url.host == "localhost\\SQLEXPRESS"
    assert url.port is None  # named instances resolve their port via SQL Browser
    (conn_str,), _ = connect_args(url)
    assert "Server=localhost\\SQLEXPRESS" in conn_str
    assert "PWD={p@ss:w/rd;{x}}}" in conn_str
    assert "TrustServerCertificate=yes" in conn_str
    assert f"DRIVER={{{settings.MSSQL_ODBC_DRIVER}}}" in conn_str


def test_mssql_windows_authentication_omits_credentials():
    spec = ConnectionSpec(
        db_type="mssql",
        host="db01",
        port=1433,
        username="ignored",
        password="ignored",
        options={"trusted_connection": True, "encrypt": False},
    )
    (conn_str,), _ = connect_args(build_url(spec))
    assert "Trusted_Connection=Yes" in conn_str
    assert "UID=" not in conn_str and "PWD=" not in conn_str
    assert "Encrypt=no" in conn_str


def test_oracle_uses_service_name():
    url = build_url(ConnectionSpec(db_type="oracle", host="ora", database="XEPDB1", username="u", password="p"))
    assert url.drivername == "oracle+oracledb"
    assert url.port == 1521
    assert url.query["service_name"] == "XEPDB1"


def test_oracle_requires_service_name():
    with pytest.raises(ConnectorError, match="service name"):
        build_url(ConnectionSpec(db_type="oracle", host="ora"))


def test_postgres_defaults_and_ssl_mode():
    url = build_url(ConnectionSpec(db_type="postgresql", host="pg", database="db", options={"sslmode": "require"}))
    assert url.port == 5432
    assert url.query["sslmode"] == "require"


def test_host_is_required_for_server_databases():
    with pytest.raises(ConnectorError, match="Host"):
        build_url(ConnectionSpec(db_type="postgresql", database="db"))


def test_unknown_database_type():
    with pytest.raises(ConnectorError, match="Unsupported"):
        build_url(ConnectionSpec(db_type="db2", host="x"))


@pytest.mark.parametrize("name", ["../abiet.db", "/etc/passwd", "../../x.sqlite", "sub/../../abiet.db"])
def test_sqlite_paths_cannot_escape_the_databases_folder(name):
    with pytest.raises(ConnectorError, match="must be inside"):
        resolve_sqlite_path(name)


def test_sqlite_read_only_connections_open_in_read_only_mode():
    ensure_demo_database()
    url = build_url(ConnectionSpec(db_type="sqlite", database=DEMO_FILE_NAME, read_only=True))
    assert url.query == {"mode": "ro", "uri": "true"}
    engine = create_engine_for(ConnectionSpec(db_type="sqlite", database=DEMO_FILE_NAME, read_only=True))
    with engine.connect() as conn, pytest.raises(Exception, match="readonly"):
        conn.exec_driver_sql("DELETE FROM regions")


def test_missing_sqlite_file():
    with pytest.raises(ConnectorError, match="not found"):
        build_url(ConnectionSpec(db_type="sqlite", database="missing.sqlite"))


def test_connection_test_reports_success_and_failure():
    ensure_demo_database()
    result = check_connection(ConnectionSpec(db_type="sqlite", database=DEMO_FILE_NAME))
    assert result["ok"] and result["server_version"]
    with pytest.raises(ConnectorError):
        check_connection(ConnectionSpec(db_type="postgresql", host="127.0.0.1", port=1, database="x", username="u"))


def test_describe_error_explains_missing_odbc_driver():
    message = describe_error(Exception("('IM002', '[IM002] [unixODBC][Driver Manager]Data source name not found')"))
    assert "ODBC driver" in message and "IM002" in message


def test_introspection_reads_tables_views_keys_and_sample_values():
    ensure_demo_database()
    spec = ConnectionSpec(db_type="sqlite", database=DEMO_FILE_NAME)
    schema = introspect_schema(create_engine_for(spec), spec)
    tables = {t["name"]: t for t in schema["tables"]}
    assert {"customers", "orders", "order_items", "products", "order_revenue"} <= set(tables)
    assert tables["order_revenue"]["kind"] == "view"
    orders = {c["name"]: c for c in tables["orders"]["columns"]}
    assert orders["order_id"]["primary_key"]
    assert orders["status"]["values"] == ["Cancelled", "Delivered", "Processing", "Returned", "Shipped"]
    assert "values" not in {c["name"]: c for c in tables["customers"]["columns"]}["contact_email"]  # personal data
    fk = next(f for f in tables["orders"]["foreign_keys"] if f["referred_table"] == "customers")
    assert fk["columns"] == ["customer_id"]
    assert not any("_type_obj" in c for t in schema["tables"] for c in t["columns"])


def test_introspection_can_skip_value_sampling():
    ensure_demo_database()
    spec = ConnectionSpec(db_type="sqlite", database=DEMO_FILE_NAME, options={"sample_values": False})
    schema = introspect_schema(create_engine_for(spec), spec)
    assert not any("values" in c for t in schema["tables"] for c in t["columns"])


def test_demo_database_is_deterministic_and_rebuilt_only_when_needed():
    path = ensure_demo_database()
    mtime = path.stat().st_mtime_ns
    assert ensure_demo_database().stat().st_mtime_ns == mtime
    import sqlite3

    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 2600
        assert db.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 180
