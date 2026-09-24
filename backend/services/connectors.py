"""
Connecting to user databases: supported types, URL building, engine caching,
connection tests and schema introspection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Column, MetaData, String, Table, create_engine, distinct, event, inspect, select
from sqlalchemy.engine import URL, Engine
from sqlalchemy.engine.reflection import ObjectKind
from sqlalchemy.exc import DBAPIError, NoSuchModuleError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from backend.config import settings
from backend.models import DatabaseConnection
from backend.security import decrypt_secret

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """A user-facing problem connecting to or reading from a database."""


@dataclass(frozen=True)
class DbType:
    key: str
    label: str
    driver: str
    sqlglot_dialect: str
    default_port: int | None
    options: tuple[dict[str, Any], ...] = ()
    requires_host: bool = True


_SCHEMAS_OPTION = {
    "key": "schemas",
    "label": "Schemas",
    "type": "text",
    "help": "Comma-separated schemas to include (default: the user's default schema)",
}
_SAMPLE_OPTION = {
    "key": "sample_values",
    "label": "Sample column values",
    "type": "bool",
    "default": True,
    "help": "Read a few distinct values of short text columns so the AI knows valid filter values",
}

DB_TYPES: dict[str, DbType] = {
    "mssql": DbType(
        key="mssql",
        label="Microsoft SQL Server",
        driver="mssql+pyodbc",
        sqlglot_dialect="tsql",
        default_port=1433,
        options=(
            {"key": "instance", "label": "Instance name", "type": "text", "help": "e.g. SQLEXPRESS (leave port empty)"},
            {"key": "trusted_connection", "label": "Windows authentication", "type": "bool", "default": False},
            {"key": "trust_server_certificate", "label": "Trust server certificate", "type": "bool", "default": True},
            {"key": "encrypt", "label": "Encrypt connection", "type": "bool", "default": True},
            {"key": "driver", "label": "ODBC driver", "type": "text", "help": "Default: " + settings.MSSQL_ODBC_DRIVER},
            _SCHEMAS_OPTION,
            _SAMPLE_OPTION,
        ),
    ),
    "postgresql": DbType(
        key="postgresql",
        label="PostgreSQL",
        driver="postgresql+psycopg2",
        sqlglot_dialect="postgres",
        default_port=5432,
        options=(
            {"key": "sslmode", "label": "SSL mode", "type": "text", "help": "disable, prefer, require, verify-full"},
            _SCHEMAS_OPTION,
            _SAMPLE_OPTION,
        ),
    ),
    "oracle": DbType(
        key="oracle",
        label="Oracle",
        driver="oracle+oracledb",
        sqlglot_dialect="oracle",
        default_port=1521,
        options=(_SCHEMAS_OPTION, _SAMPLE_OPTION),
    ),
    "mysql": DbType(
        key="mysql",
        label="MySQL / MariaDB",
        driver="mysql+pymysql",
        sqlglot_dialect="mysql",
        default_port=3306,
        options=(_SAMPLE_OPTION,),
    ),
    "sqlite": DbType(
        key="sqlite",
        label="SQLite",
        driver="sqlite",
        sqlglot_dialect="sqlite",
        default_port=None,
        options=(_SAMPLE_OPTION,),
        requires_host=False,
    ),
}


@dataclass
class ConnectionSpec:
    db_type: str
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True

    @classmethod
    def from_model(cls, conn: DatabaseConnection) -> ConnectionSpec:
        return cls(
            db_type=conn.db_type,
            host=conn.host,
            port=conn.port,
            database=conn.database,
            username=conn.username,
            password=decrypt_secret(conn.password_encrypted),
            options=dict(conn.options or {}),
            read_only=conn.read_only,
        )

    @property
    def type_info(self) -> DbType:
        try:
            return DB_TYPES[self.db_type]
        except KeyError:
            raise ConnectorError(f"Unsupported database type '{self.db_type}'") from None

    def schemas(self) -> list[str | None]:
        raw = self.options.get("schemas") or ""
        names = [s.strip() for s in str(raw).split(",") if s.strip()]
        return names or [None]


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def resolve_sqlite_path(database: str | None) -> Path:
    """Resolve a SQLite file name, refusing anything outside the allowed directory."""
    if not database:
        raise ConnectorError("Enter the SQLite file name")
    base = settings.sqlite_dir
    path = (base / database).resolve()
    if not path.is_relative_to(base):
        raise ConnectorError(f"SQLite files must be inside {base}")
    return path


def build_url(spec: ConnectionSpec) -> URL:
    info = spec.type_info
    if info.requires_host and not spec.host:
        raise ConnectorError("Host is required")

    if spec.db_type == "sqlite":
        path = resolve_sqlite_path(spec.database)
        if not path.exists():
            raise ConnectorError(f"SQLite file '{spec.database}' was not found in {settings.sqlite_dir}")
        if spec.read_only:
            return URL.create("sqlite", database=f"file:{path}", query={"mode": "ro", "uri": "true"})
        return URL.create("sqlite", database=str(path))

    opts = spec.options
    if spec.db_type == "mssql":
        host = spec.host
        port = spec.port
        if opts.get("instance"):
            host = f"{spec.host}\\{opts['instance']}"
            port = None  # named instances are resolved by the SQL Browser service
        query = {"driver": opts.get("driver") or settings.MSSQL_ODBC_DRIVER}
        if _truthy(opts.get("trust_server_certificate"), True):
            query["TrustServerCertificate"] = "yes"
        query["Encrypt"] = "yes" if _truthy(opts.get("encrypt"), True) else "no"
        trusted = _truthy(opts.get("trusted_connection"))
        return URL.create(
            info.driver,
            username=None if trusted else spec.username,
            password=None if trusted else spec.password,
            host=host,
            port=port,
            database=spec.database or None,
            query=query,
        )

    if spec.db_type == "oracle":
        if not spec.database:
            raise ConnectorError("Enter the Oracle service name (e.g. XEPDB1)")
        return URL.create(
            info.driver,
            username=spec.username,
            password=spec.password,
            host=spec.host,
            port=spec.port or info.default_port,
            query={"service_name": spec.database},
        )

    query: dict[str, str] = {}
    if spec.db_type == "postgresql" and opts.get("sslmode"):
        query["sslmode"] = str(opts["sslmode"])
    if spec.db_type == "mysql":
        query["charset"] = "utf8mb4"
    return URL.create(
        info.driver,
        username=spec.username,
        password=spec.password,
        host=spec.host,
        port=spec.port or info.default_port,
        database=spec.database or None,
        query=query,
    )


def _connect_args(spec: ConnectionSpec) -> dict[str, Any]:
    connect_timeout = settings.CONNECT_TIMEOUT_SECONDS
    query_timeout = settings.QUERY_TIMEOUT_SECONDS
    if spec.db_type == "postgresql":
        return {
            "connect_timeout": connect_timeout,
            "application_name": "abiet",
            "options": f"-c statement_timeout={query_timeout * 1000}",
        }
    if spec.db_type == "mysql":
        # read_timeout is only a backstop; the server-side limit is set in _install_timeouts.
        return {"connect_timeout": connect_timeout, "read_timeout": query_timeout + 15}
    if spec.db_type == "mssql":
        return {"timeout": connect_timeout}
    if spec.db_type == "oracle":
        return {"tcp_connect_timeout": connect_timeout}
    if spec.db_type == "sqlite":
        return {"check_same_thread": False, "timeout": connect_timeout}
    return {}


def _install_timeouts(engine: Engine, db_type: str) -> None:
    """Apply per-query timeouts for drivers that set them on the DBAPI connection."""
    query_timeout = settings.QUERY_TIMEOUT_SECONDS

    if db_type == "mssql":

        @event.listens_for(engine, "connect")
        def _mssql_timeout(dbapi_conn, _record):  # pragma: no cover - needs SQL Server
            dbapi_conn.timeout = query_timeout

    elif db_type == "oracle":

        @event.listens_for(engine, "connect")
        def _oracle_timeout(dbapi_conn, _record):  # pragma: no cover - needs Oracle
            dbapi_conn.call_timeout = query_timeout * 1000

    elif db_type == "mysql":

        @event.listens_for(engine, "connect")
        def _mysql_timeout(dbapi_conn, _record):
            # Server-side limit so the server stops the statement (the socket read timeout only
            # drops the client). MySQL and MariaDB name the variable differently.
            cursor = dbapi_conn.cursor()
            try:
                for statement in (
                    f"SET SESSION max_execution_time = {query_timeout * 1000}",
                    f"SET SESSION max_statement_time = {query_timeout}",
                ):
                    try:
                        cursor.execute(statement)
                        break
                    except Exception:  # noqa: BLE001 - unknown variable on this server flavour
                        continue
            finally:
                cursor.close()

    elif db_type == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_handler(dbapi_conn, record):
            deadline = [math.inf]
            record.info["abiet_deadline"] = deadline
            dbapi_conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline[0] else 0, 10000)

        @event.listens_for(engine, "before_cursor_execute")
        def _sqlite_deadline(conn, *_args):
            deadline = conn.info.get("abiet_deadline")
            if deadline is not None:
                deadline[0] = time.monotonic() + query_timeout


def create_engine_for(spec: ConnectionSpec, *, pooled: bool = True) -> Engine:
    url = build_url(spec)
    kwargs: dict[str, Any] = {"connect_args": _connect_args(spec), "pool_pre_ping": True}
    if pooled:
        if spec.db_type != "sqlite":
            kwargs.update(pool_size=2, max_overflow=3, pool_recycle=1800)
    else:
        kwargs["poolclass"] = NullPool
    try:
        engine = create_engine(url, **kwargs)
    except (ImportError, NoSuchModuleError) as exc:
        hint = ""
        if spec.db_type == "mssql":
            hint = " Install unixODBC and the Microsoft ODBC Driver for SQL Server."
        raise ConnectorError(f"The {spec.type_info.label} driver is not available: {exc}.{hint}") from exc
    _install_timeouts(engine, spec.db_type)
    return engine


_engine_cache: dict[int, tuple[Any, Engine]] = {}
_engine_lock = threading.Lock()


def connection_fingerprint(conn: DatabaseConnection) -> str:
    """Identifies the settings an engine was built from (not the cached schema)."""
    parts = [conn.db_type, conn.host, conn.port, conn.database, conn.username, conn.password_encrypted,
             json.dumps(conn.options or {}, sort_keys=True, default=str), conn.read_only]  # fmt: skip
    return hashlib.sha256(repr(parts).encode()).hexdigest()


def get_engine(conn: DatabaseConnection) -> Engine:
    """Return a pooled engine for a saved connection, rebuilt when its settings change."""
    version = connection_fingerprint(conn)
    with _engine_lock:
        cached = _engine_cache.get(conn.id)
        if cached and cached[0] == version:
            return cached[1]
        if cached:
            cached[1].dispose()
        engine = create_engine_for(ConnectionSpec.from_model(conn))
        _engine_cache[conn.id] = (version, engine)
        return engine


def dispose_engine(connection_id: int) -> None:
    with _engine_lock:
        cached = _engine_cache.pop(connection_id, None)
    if cached:
        cached[1].dispose()


def dispose_all() -> None:
    with _engine_lock:
        engines = [e for _, e in _engine_cache.values()]
        _engine_cache.clear()
    for engine in engines:
        engine.dispose()


def describe_error(exc: BaseException) -> str:
    """Turn a driver exception into a short message safe to show the user."""
    if isinstance(exc, ConnectorError):
        return str(exc)
    if isinstance(exc, DBAPIError) and exc.orig is not None:
        message = str(exc.orig)
    else:
        message = str(exc)
    message = message.split("\n(Background on this error")[0].strip()
    lowered = message.lower()
    if (
        message == "interrupted"
        or "max_statement_time exceeded" in lowered
        or ("maximum statement execution time exceeded" in lowered)
        or ("lost connection" in lowered and "timed out" in lowered)
    ):
        message = f"The query was stopped because it ran longer than {settings.QUERY_TIMEOUT_SECONDS} seconds"
    elif "IM002" in message or "Can't open lib" in message:
        message = (
            "The ODBC driver for SQL Server is not installed on the ABIET server, or the driver name is wrong. "
            "Install 'Microsoft ODBC Driver 18 for SQL Server' (the ABIET Docker image includes it) or set the "
            f"ODBC driver option. Details: {message}"
        )
    return message[:1500] or exc.__class__.__name__


def test_connection(spec: ConnectionSpec) -> dict[str, Any]:
    started = time.monotonic()
    engine = create_engine_for(spec, pooled=False)
    try:
        with engine.connect() as conn:
            version = conn.dialect.server_version_info
            conn.rollback()
    except SQLAlchemyError as exc:
        raise ConnectorError(describe_error(exc)) from exc
    finally:
        engine.dispose()
    return {
        "ok": True,
        "message": "Connection successful",
        "server_version": ".".join(str(p) for p in version) if version else None,
        "latency_ms": int((time.monotonic() - started) * 1000),
    }


# --- Schema introspection ----------------------------------------------------

_TEXT_TYPES = ("CHAR", "TEXT", "STRING", "CLOB")
# Columns never sampled: personal data (values are sent to the AI provider) and free text.
_FREE_TEXT_HINTS = (
    "name", "email", "mail", "phone", "address", "street", "zip", "postcode", "ssn", "birth",
    "password", "secret", "hash", "token", "uuid", "guid", "description", "comment", "note",
    "message", "body", "url", "path",
)  # fmt: skip
SAMPLE_MAX_VALUES = 10
SAMPLE_SCAN_ROWS = 10000
SAMPLE_TIME_BUDGET_SECONDS = 15.0
SAMPLE_MAX_TABLES = 80


def _type_name(col_type: Any) -> str:
    item_type = getattr(col_type, "item_type", None)
    if item_type is not None:  # PostgreSQL arrays
        return f"{_type_name(item_type)}[]"
    try:
        return str(col_type)
    except Exception:  # noqa: BLE001 - some reflected types cannot compile generically
        return col_type.__class__.__name__


def _is_sampleable(column: dict[str, Any]) -> bool:
    type_name = column["type"].upper()
    if not any(t in type_name for t in _TEXT_TYPES):
        return False
    if column.get("primary_key"):
        return False
    name = column["name"].lower()
    if any(hint in name for hint in _FREE_TEXT_HINTS):
        return False
    length = getattr(column.get("_type_obj"), "length", None)
    return length is None or length <= 100


def _reflect_schema(insp, schema: str | None, max_tables: int) -> tuple[list[dict[str, Any]], bool]:
    tables = [(name, "table") for name in insp.get_table_names(schema=schema)]
    try:
        tables += [(name, "view") for name in insp.get_view_names(schema=schema)]
    except NotImplementedError:  # pragma: no cover - dialect without views
        pass
    truncated = len(tables) > max_tables
    tables = tables[:max_tables]
    names = [name for name, _ in tables]
    if not names:
        return [], truncated

    try:
        columns = insp.get_multi_columns(schema=schema, filter_names=names, kind=ObjectKind.ANY)
        pks = insp.get_multi_pk_constraint(schema=schema, filter_names=names, kind=ObjectKind.ANY)
        fks = insp.get_multi_foreign_keys(schema=schema, filter_names=names, kind=ObjectKind.ANY)
    except (NotImplementedError, SQLAlchemyError):
        columns, pks, fks = {}, {}, {}
        for name in names:
            key = (schema, name)
            try:
                columns[key] = insp.get_columns(name, schema=schema)
                pks[key] = insp.get_pk_constraint(name, schema=schema)
                fks[key] = insp.get_foreign_keys(name, schema=schema)
            except SQLAlchemyError as exc:
                logger.warning("Could not reflect %s.%s: %s", schema, name, describe_error(exc))

    result = []
    for name, kind in tables:
        key = (schema, name)
        pk_cols = set((pks.get(key) or {}).get("constrained_columns") or [])
        cols = []
        for col in columns.get(key, []):
            entry = {
                "name": col["name"],
                "type": _type_name(col["type"]),
                "nullable": bool(col.get("nullable", True)),
                "primary_key": col["name"] in pk_cols,
                "_type_obj": col["type"],
            }
            if col.get("comment"):
                entry["comment"] = col["comment"]
            cols.append(entry)
        result.append(
            {
                "schema": schema,
                "name": name,
                "kind": kind,
                "columns": cols,
                "foreign_keys": [
                    {
                        "columns": fk["constrained_columns"],
                        "referred_schema": fk.get("referred_schema"),
                        "referred_table": fk["referred_table"],
                        "referred_columns": fk["referred_columns"],
                    }
                    for fk in fks.get(key, [])
                ],
            }
        )
    return result, truncated


def _sample_values(engine: Engine, tables: list[dict[str, Any]]) -> None:
    """Attach up to ``SAMPLE_MAX_VALUES`` distinct values to short categorical text columns."""
    deadline = time.monotonic() + SAMPLE_TIME_BUDGET_SECONDS
    with engine.connect() as conn:
        for table in tables[:SAMPLE_MAX_TABLES]:
            if table["kind"] != "table":
                continue
            for col in table["columns"]:
                if time.monotonic() > deadline:
                    conn.rollback()
                    return
                if not _is_sampleable(col):
                    continue
                t = Table(table["name"], MetaData(), Column(col["name"], String), schema=table["schema"])
                inner = select(t.c[col["name"]]).limit(SAMPLE_SCAN_ROWS).subquery()
                stmt = select(distinct(inner.c[col["name"]])).limit(SAMPLE_MAX_VALUES + 1)
                try:
                    values = [row[0] for row in conn.execute(stmt)]
                except SQLAlchemyError as exc:
                    logger.debug("Sampling %s.%s failed: %s", table["name"], col["name"], describe_error(exc))
                    conn.rollback()
                    continue
                values = [v for v in values if v is not None and str(v).strip()]
                if 0 < len(values) <= SAMPLE_MAX_VALUES:
                    col["values"] = sorted(str(v)[:60] for v in values)
        conn.rollback()


def introspect_schema(engine: Engine, spec: ConnectionSpec) -> dict[str, Any]:
    started = time.monotonic()
    try:
        insp = inspect(engine)
        tables: list[dict[str, Any]] = []
        truncated = False
        remaining = settings.SCHEMA_MAX_TABLES
        for schema in spec.schemas():
            if remaining <= 0:
                truncated = True
                break
            found, cut = _reflect_schema(insp, schema, remaining)
            tables.extend(found)
            truncated = truncated or cut
            remaining -= len(found)
        if _truthy(spec.options.get("sample_values"), True):
            try:
                _sample_values(engine, tables)
            except SQLAlchemyError as exc:
                logger.warning("Value sampling skipped: %s", describe_error(exc))
    except SQLAlchemyError as exc:
        raise ConnectorError(describe_error(exc)) from exc

    for table in tables:
        for col in table["columns"]:
            col.pop("_type_obj", None)
    return {
        "dialect": spec.db_type,
        "tables": tables,
        "truncated": truncated,
        "introspected_at": datetime.now(UTC).isoformat(),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
