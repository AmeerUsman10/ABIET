"""
Asking questions and running SQL.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ai.learning.learning_engine import LearningEngine
from ai.llm import LLMClient, get_llm
from backend.database import get_db
from backend.deps import enforce_ai_rate_limit, get_current_user, get_owned_connection, get_owned_query
from backend.models import User
from backend.routes.history import to_query_out
from backend.schemas import AskRequest, AskResponse, ResultOut, RunRequest
from backend.services import assistant
from backend.services.demo import ensure_demo_database

logger = logging.getLogger(__name__)
router = APIRouter()


def _response(outcome: assistant.Outcome) -> AskResponse:
    result = outcome.result
    return AskResponse(
        query=to_query_out(outcome.record),
        result=ResultOut(
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
            truncated=result.truncated,
            duration_ms=result.duration_ms,
            affected_rows=result.affected_rows,
        )
        if result
        else None,
        clarification=outcome.clarification,
        requires_confirmation=outcome.requires_confirmation,
        chart=outcome.chart,
    )


@router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    user: User = Depends(enforce_ai_rate_limit),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
):
    """Answer a natural-language question: generate SQL, check it, run it, and repair it if it fails."""
    conn = get_owned_connection(db, user, payload.connection_id)
    if payload.parent_id is not None:
        get_owned_query(db, user, payload.parent_id)
    if conn.is_demo:
        ensure_demo_database()
    outcome = assistant.ask(db, user, conn, payload.question, llm, parent_id=payload.parent_id, execute=payload.execute)
    logger.info("Query %s by %s: %s", outcome.record.id, user.username, outcome.record.status)
    return _response(outcome)


@router.post("/run", response_model=AskResponse)
def run(payload: RunRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Run SQL written or edited by the user. Write statements need a writable connection and confirmation."""
    conn = get_owned_connection(db, user, payload.connection_id)
    record = None
    if payload.query_id is not None:
        record = get_owned_query(db, user, payload.query_id)
        if record.connection_id != conn.id:
            raise HTTPException(status_code=400, detail="That query belongs to a different connection")
    if conn.is_demo:
        ensure_demo_database()
    try:
        outcome = assistant.run_sql(
            db, user, conn, payload.sql, record=record, question=payload.question, confirm_write=payload.confirm_write
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _response(outcome)


@router.get("/suggestions", response_model=list[str])
def suggestions(
    connection_id: int | None = None,
    q: str = Query("", max_length=200),
    limit: int = Query(8, ge=1, le=25),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Previously successful questions matching what the user is typing."""
    if connection_id is not None:
        get_owned_connection(db, user, connection_id)
    return LearningEngine(db).get_query_suggestions(user.id, connection_id, q, limit)
