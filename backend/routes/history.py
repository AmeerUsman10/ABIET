"""
Query history, saved queries, feedback and CSV export.
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ai.learning.learning_engine import LearningEngine
from backend.config import settings
from backend.database import get_db
from backend.deps import get_current_user, get_owned_query, query_connection
from backend.models import DatabaseConnection, QueryRecord, User
from backend.schemas import FeedbackRequest, QueryList, QueryOut, QueryUpdate
from backend.services.assistant import sqlglot_dialect
from backend.services.connectors import get_engine
from backend.services.demo import ensure_demo_database
from backend.services.executor import QueryExecutionError, stream_csv
from backend.services.sql_guard import SqlRejected, analyze_sql

router = APIRouter()

STATUSES = {"success", "error", "blocked", "clarification", "needs_confirmation", "generated"}


def to_query_out(record: QueryRecord) -> QueryOut:
    out = QueryOut.model_validate(record)
    conn = query_connection(record)
    out.connection_name = conn.name if conn else None
    if conn is None:
        out.connection_id = None
    return out


@router.get("", response_model=QueryList)
def list_queries(
    connection_id: int | None = None,
    saved: bool | None = None,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, max_length=200),
    rated: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conditions = [QueryRecord.user_id == user.id]
    if connection_id is not None:
        conditions.append(QueryRecord.connection_id == connection_id)
    if saved is not None:
        conditions.append(QueryRecord.is_saved.is_(saved))
    if status_filter:
        if status_filter not in STATUSES:
            raise HTTPException(status_code=422, detail=f"Unknown status '{status_filter}'")
        conditions.append(QueryRecord.status == status_filter)
    if rated is not None:
        conditions.append(QueryRecord.rating.is_not(None) if rated else QueryRecord.rating.is_(None))
    if search:
        pattern = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(QueryRecord.question).like(pattern),
                func.lower(QueryRecord.title).like(pattern),
                func.lower(QueryRecord.executed_sql).like(pattern),
            )
        )
    total = db.scalar(select(func.count(QueryRecord.id)).where(*conditions)) or 0
    records = db.scalars(
        select(QueryRecord)
        .where(*conditions)
        .order_by(QueryRecord.created_at.desc(), QueryRecord.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return QueryList(items=[to_query_out(r) for r in records], total=total)


@router.get("/{query_id}", response_model=QueryOut)
def get_query(query_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return to_query_out(get_owned_query(db, user, query_id))


@router.patch("/{query_id}", response_model=QueryOut)
def update_query(
    query_id: int, payload: QueryUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    record = get_owned_query(db, user, query_id)
    changes = payload.model_dump(exclude_unset=True)
    if "is_saved" in changes and changes["is_saved"] is not None:
        record.is_saved = changes["is_saved"]
        if record.is_saved and not record.title and "title" not in changes:
            record.title = (record.question or "Saved query")[:200]
    if "title" in changes:
        record.title = (changes["title"] or "").strip() or None
    db.commit()
    return to_query_out(record)


@router.delete("/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_query(query_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = get_owned_query(db, user, query_id)
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{query_id}/feedback", response_model=QueryOut)
def submit_feedback(
    query_id: int, payload: FeedbackRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Rate an answer and optionally supply the correct SQL. Both feed the learning engine."""
    record = get_owned_query(db, user, query_id)
    corrected = payload.corrected_sql
    if corrected is not None and corrected.strip():
        conn = query_connection(record)
        dialect = sqlglot_dialect(conn) if conn else "sqlite"
        try:
            corrected = analyze_sql(corrected, dialect).sql
        except SqlRejected as exc:
            raise HTTPException(status_code=400, detail=f"Corrected SQL: {exc}") from exc
    LearningEngine(db).record_feedback(record, rating=payload.rating, comment=payload.comment, corrected_sql=corrected)
    return to_query_out(record)


@router.get("/{query_id}/export.csv")
def export_csv(query_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Re-run a query's SQL and download the full result (up to EXPORT_MAX_ROWS rows) as CSV."""
    record = get_owned_query(db, user, query_id)
    conn: DatabaseConnection | None = query_connection(record)
    sql = record.executed_sql or record.generated_sql
    if conn is None or not sql:
        raise HTTPException(status_code=400, detail="This query has no SQL or its connection was deleted")
    try:
        analysis = analyze_sql(sql, sqlglot_dialect(conn))
    except SqlRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not analysis.is_read_only:
        raise HTTPException(status_code=400, detail="Only read-only queries can be exported")
    if conn.is_demo:
        ensure_demo_database()
    engine = get_engine(conn)
    rows = stream_csv(engine, conn.db_type, analysis.sql, max_rows=settings.EXPORT_MAX_ROWS)
    try:
        first = next(rows)  # surface SQL errors as a proper HTTP error before streaming starts
    except QueryExecutionError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except StopIteration:
        first = ""

    def body():
        yield first
        yield from rows

    base = re.sub(r"[^A-Za-z0-9]+", "-", (record.title or record.question or f"query-{record.id}")).strip("-")
    filename = f"{base[:60] or 'query'}-{record.id}.csv"
    return StreamingResponse(
        body(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
