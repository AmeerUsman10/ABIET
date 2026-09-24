"""
The ask/run workflow: question -> SQL -> safety check -> execution (with
automatic repair) -> recorded history that the learning engine uses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ai.learning.learning_engine import LearningEngine
from ai.llm import LLMClient, LLMError, LLMNotConfigured
from ai.nlp.prompts import Turn
from ai.nlp.query_processor import GenerationResult, QueryProcessor
from backend.config import settings
from backend.models import DatabaseConnection, QueryRecord, User, utcnow
from backend.services.connectors import (
    DB_TYPES,
    ConnectionSpec,
    ConnectorError,
    get_engine,
    introspect_schema,
)
from backend.services.executor import ExecutionResult, QueryExecutionError, execute_sql
from backend.services.sql_guard import SqlAnalysis, SqlRejected, analyze_sql

logger = logging.getLogger(__name__)


@dataclass
class Outcome:
    record: QueryRecord
    result: ExecutionResult | None = None
    clarification: str | None = None
    requires_confirmation: bool = False
    chart: dict[str, Any] | None = None


def sqlglot_dialect(conn: DatabaseConnection) -> str:
    return DB_TYPES[conn.db_type].sqlglot_dialect


def get_schema(db: Session, conn: DatabaseConnection, *, refresh: bool = False) -> dict[str, Any]:
    """Cached schema for a connection; introspects on first use or when ``refresh`` is set."""
    if conn.schema_cache and not refresh:
        return conn.schema_cache
    schema = introspect_schema(get_engine(conn), ConnectionSpec.from_model(conn))
    conn.schema_cache = schema
    conn.schema_cached_at = utcnow()
    db.commit()
    return schema


def conversation_history(db: Session, user: User, parent_id: int | None, connection_id: int) -> list[Turn]:
    """Earlier turns of a follow-up conversation, oldest first."""
    turns: list[Turn] = []
    current = parent_id
    seen: set[int] = set()
    while current and len(turns) < settings.AI_FOLLOW_UP_DEPTH and current not in seen:
        seen.add(current)
        record = db.get(QueryRecord, current)
        if record is None or record.user_id != user.id or record.connection_id != connection_id:
            break
        if record.question:
            turns.append(
                Turn(
                    question=record.question,
                    sql=record.corrected_sql or record.executed_sql or record.generated_sql,
                    explanation=record.explanation,
                )
            )
        current = record.parent_id
    return list(reversed(turns))


def _fail(db: Session, record: QueryRecord, status: str, message: str) -> None:
    record.status = status
    record.error = message
    db.commit()


def _run(
    db: Session, record: QueryRecord, conn: DatabaseConnection, analysis: SqlAnalysis
) -> tuple[ExecutionResult | None, bool]:
    """
    Execute and record the outcome. Returns ``(result, connection_failed)``;
    ``result`` is None when execution failed.
    """
    record.executed_sql = analysis.sql
    try:
        result = execute_sql(
            get_engine(conn),
            conn.db_type,
            analysis.sql,
            max_rows=settings.QUERY_MAX_ROWS,
            read_only=analysis.is_read_only,
        )
    except ConnectorError as exc:
        _fail(db, record, "error", str(exc))
        return None, True
    except QueryExecutionError as exc:
        _fail(db, record, "error", exc.message)
        return None, exc.connection_error
    record.status = "success"
    record.error = None
    record.row_count = result.row_count if result.affected_rows is None else result.affected_rows
    record.duration_ms = result.duration_ms
    db.commit()
    return result, False


def _check(db: Session, record: QueryRecord, conn: DatabaseConnection, sql: str) -> SqlAnalysis | None:
    """Safety-check AI output. Returns the analysis if it may run now, else records why not."""
    try:
        analysis = analyze_sql(sql, sqlglot_dialect(conn))
    except SqlRejected as exc:
        _fail(db, record, "blocked", str(exc))
        return None
    if not analysis.is_read_only:
        if conn.read_only:
            _fail(db, record, "blocked", f"{analysis.reason}. This connection is read-only.")
        else:
            record.status = "needs_confirmation"
            record.error = None
            db.commit()
        return None
    return analysis


def ask(
    db: Session,
    user: User,
    conn: DatabaseConnection,
    question: str,
    llm: LLMClient,
    *,
    parent_id: int | None = None,
    execute: bool = True,
) -> Outcome:
    schema = get_schema(db, conn)
    history = conversation_history(db, user, parent_id, conn.id)
    learning = LearningEngine(db)
    examples = learning.find_similar_patterns(conn.id, question, limit=settings.AI_FEW_SHOT_EXAMPLES)
    processor = QueryProcessor(llm, max_rows=settings.QUERY_MAX_ROWS, schema_budget=settings.AI_SCHEMA_CHAR_BUDGET)
    context = {
        "db_type": conn.db_type,
        "schema": schema,
        "examples": examples,
        "history": history,
        "allow_writes": not conn.read_only,
    }

    record = QueryRecord(
        user_id=user.id,
        connection_id=conn.id,
        parent_id=parent_id if history else None,
        question=question.strip(),
        status="generated",
    )
    db.add(record)

    try:
        generation = processor.generate(question, **context)
    except LLMNotConfigured:
        db.rollback()
        raise
    except LLMError as exc:
        _fail(db, record, "error", f"AI service error: {exc}")
        return Outcome(record)

    record.generated_sql = generation.sql
    record.explanation = generation.explanation
    if not generation.sql:
        record.status = "clarification"
        db.commit()
        return Outcome(record, clarification=generation.clarification)

    analysis = _check(db, record, conn, generation.sql)
    if analysis is None:
        return Outcome(record, requires_confirmation=record.status == "needs_confirmation", chart=generation.chart)
    if not execute:
        db.commit()
        return Outcome(record, chart=generation.chart)

    result, connection_failed = _run(db, record, conn, analysis)
    attempts = 0
    while result is None and not connection_failed and attempts < settings.AI_MAX_REPAIR_ATTEMPTS:
        attempts += 1
        failed_sql, failed_error = analysis.sql, record.error or ""
        try:
            repaired: GenerationResult = processor.repair(question, failed_sql, failed_error, **context)
        except LLMError as exc:
            logger.info("Repair attempt failed: %s", exc)
            break
        if not repaired.sql or repaired.sql.strip() == failed_sql.strip():
            break
        new_analysis = _check(db, record, conn, repaired.sql)
        if new_analysis is None:
            if record.status == "needs_confirmation":
                record.status = "error"
                record.error = failed_error
                db.commit()
            break
        analysis = new_analysis
        record.repaired = True
        if repaired.explanation:
            record.explanation = repaired.explanation
        if repaired.chart:
            generation.chart = repaired.chart
        result, connection_failed = _run(db, record, conn, analysis)

    return Outcome(record, result=result, chart=generation.chart)


def run_sql(
    db: Session,
    user: User,
    conn: DatabaseConnection,
    sql: str,
    *,
    record: QueryRecord | None = None,
    question: str | None = None,
    confirm_write: bool = False,
) -> Outcome:
    """Run SQL written or edited by the user (optionally updating an existing history record)."""
    try:
        analysis = analyze_sql(sql, sqlglot_dialect(conn))
    except SqlRejected as exc:
        raise ValueError(str(exc)) from exc

    if record is None:
        record = QueryRecord(
            user_id=user.id,
            connection_id=conn.id,
            question=(question or "").strip() or None,
            status="generated",
        )
        db.add(record)
    elif (record.executed_sql or record.generated_sql or "").strip() != analysis.sql:
        # A rating applies to the SQL that was rated; editing the SQL withdraws it
        # so the learning engine never pairs the question with unapproved SQL.
        record.rating = None
        record.feedback_at = None
    record.repaired = False

    if not analysis.is_read_only:
        if conn.read_only:
            record.executed_sql = analysis.sql
            _fail(db, record, "blocked", f"{analysis.reason}. This connection is read-only.")
            return Outcome(record)
        if not confirm_write:
            record.executed_sql = analysis.sql
            record.status = "needs_confirmation"
            record.error = None
            db.commit()
            return Outcome(record, requires_confirmation=True)

    result, _ = _run(db, record, conn, analysis)
    return Outcome(record, result=result)
