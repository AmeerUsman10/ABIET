"""
Learning system: usage and accuracy insights, and the examples ABIET has learned.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ai.feedback_processor import FeedbackProcessor
from ai.llm import LLMClient, get_llm
from backend.database import get_db
from backend.deps import enforce_ai_rate_limit, get_current_user, get_owned_connection
from backend.models import QueryRecord, User
from backend.schemas import AIInsightsOut, InsightsOut, LearnedExample

router = APIRouter()


def _scope_user(scope: str, user: User) -> int | None:
    if scope == "all":
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="Only administrators can view instance-wide insights")
        return None
    return user.id


@router.get("/insights", response_model=InsightsOut)
def insights(
    scope: Literal["me", "all"] = "me",
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Accuracy, error and usage analysis with improvement suggestions."""
    report = FeedbackProcessor(db).export_report(user_id=_scope_user(scope, user), days=days)
    return InsightsOut(**report)


@router.post("/insights/ai", response_model=AIInsightsOut)
def ai_insights(
    scope: Literal["me", "all"] = "me",
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(enforce_ai_rate_limit),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
):
    """Ask the language model to interpret the insights and recommend improvements."""
    processor = FeedbackProcessor(db, llm)
    analysis = processor.analyze_feedback_patterns(user_id=_scope_user(scope, user), days=days)
    return AIInsightsOut(**processor.get_ai_insights(analysis))


@router.get("/examples", response_model=list[LearnedExample])
def learned_examples(
    connection_id: int,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approved and corrected queries that are reused as examples for this connection."""
    get_owned_connection(db, user, connection_id)
    records = db.scalars(
        select(QueryRecord)
        .where(
            QueryRecord.connection_id == connection_id,
            QueryRecord.question.is_not(None),
            or_(
                QueryRecord.corrected_sql.is_not(None),
                and_(QueryRecord.rating == 1, QueryRecord.status == "success"),
            ),
        )
        .order_by(QueryRecord.feedback_at.desc(), QueryRecord.id.desc())
        .limit(limit)
    )
    return [
        LearnedExample(
            query_id=r.id,
            question=r.question,
            sql=r.corrected_sql or r.executed_sql or "",
            source="corrected" if r.corrected_sql else "approved",
        )
        for r in records
    ]
