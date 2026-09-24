"""
Running SQL against user databases and serializing results.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from decimal import Decimal
from typing import Any

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from backend.services.connectors import describe_error

logger = logging.getLogger(__name__)

_STREAMING_DIALECTS = {"postgresql", "mysql"}


class QueryExecutionError(Exception):
    def __init__(self, message: str, *, connection_error: bool = False):
        super().__init__(message)
        self.message = message
        self.connection_error = connection_error


@dataclass
class ExecutionResult:
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    affected_rows: int | None = None


def to_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        if value == value.to_integral_value() and abs(value) < 2**53:
            return int(value)
        return float(value)
    if isinstance(value, (datetime, date, dt_time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<binary {len(bytes(value))} bytes>"
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [to_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_json_value(v) for k, v in value.items()}
    return str(value)


def to_csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (datetime, date, dt_time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<binary {len(bytes(value))} bytes>"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(to_json_value(value))
    return value


def _begin_read_only(conn: Connection, db_type: str) -> None:
    """Declare the transaction read-only where the database supports it."""
    statement = {
        "postgresql": "SET TRANSACTION READ ONLY",
        "mysql": "SET TRANSACTION READ ONLY",
        "oracle": "SET TRANSACTION READ ONLY",
    }.get(db_type)
    if not statement:
        return
    try:
        conn.exec_driver_sql(statement)
    except SQLAlchemyError as exc:  # pragma: no cover - depends on server
        logger.debug("Could not mark transaction read-only: %s", describe_error(exc))
        conn.rollback()


def _connect(engine: Engine) -> Connection:
    try:
        return engine.connect()
    except SQLAlchemyError as exc:
        raise QueryExecutionError(describe_error(exc), connection_error=True) from exc


def execute_sql(engine: Engine, db_type: str, sql: str, *, max_rows: int, read_only: bool = True) -> ExecutionResult:
    """
    Run one statement. Read-only execution always rolls back; write execution
    (only for connections that allow it, after confirmation) commits.
    """
    started = time.monotonic()
    conn = _connect(engine)
    with conn:
        try:
            if read_only:
                _begin_read_only(conn, db_type)
            options: dict[str, Any] = {"no_parameters": True}
            if read_only and db_type in _STREAMING_DIALECTS:
                options["stream_results"] = True
            result = conn.execution_options(**options).exec_driver_sql(sql)
            columns: list[str] = []
            rows: list[list[Any]] = []
            truncated = False
            affected = None
            if result.returns_rows:
                columns = [str(c) for c in result.keys()]
                fetched = result.fetchmany(max_rows + 1)
                truncated = len(fetched) > max_rows
                rows = [[to_json_value(v) for v in row] for row in fetched[:max_rows]]
                result.close()
            else:
                affected = result.rowcount if result.rowcount is not None and result.rowcount >= 0 else None
            if read_only:
                conn.rollback()
            else:
                conn.commit()
        except SQLAlchemyError as exc:
            conn.rollback()
            raise QueryExecutionError(describe_error(exc)) from exc
    return ExecutionResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        duration_ms=int((time.monotonic() - started) * 1000),
        affected_rows=affected,
    )


def stream_csv(engine: Engine, db_type: str, sql: str, *, max_rows: int) -> Iterator[str]:
    """Yield a read-only query's results as CSV text chunks."""
    conn = _connect(engine)
    try:
        _begin_read_only(conn, db_type)
        options: dict[str, Any] = {"no_parameters": True}
        if db_type in _STREAMING_DIALECTS:
            options["stream_results"] = True
        try:
            result = conn.execution_options(**options).exec_driver_sql(sql)
        except SQLAlchemyError as exc:
            raise QueryExecutionError(describe_error(exc)) from exc
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([str(c) for c in result.keys()])
        sent = 0
        while sent < max_rows:
            batch = result.fetchmany(min(1000, max_rows - sent))
            if not batch:
                break
            for row in batch:
                writer.writerow([to_csv_value(v) for v in row])
            sent += len(batch)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
        result.close()
        if buffer.getvalue():
            yield buffer.getvalue()
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()
