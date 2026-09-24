"""
ABIET Learning Engine
=====================
Continuous learning from user interactions.

Every question is stored in ``query_history``. When users approve a result
(thumbs up) or correct the SQL, that question/SQL pair becomes a trusted
example. For each new question the engine retrieves the most similar trusted
examples for the same database and they are included in the prompt, so the
assistant picks up each database's conventions (naming, business rules,
which table holds "revenue", ...) over time.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ai.learning.similarity import normalize_question, similarity, tokenize
from ai.nlp.prompts import Example
from backend.models import QueryRecord, utcnow

CANDIDATE_POOL = 500
MIN_SIMILARITY = 0.2


class LearningEngine:
    def __init__(self, db: Session):
        self.db = db

    def _trusted(self):
        return or_(
            QueryRecord.corrected_sql.is_not(None),
            and_(QueryRecord.rating == 1, QueryRecord.status == "success"),
        )

    def find_similar_patterns(
        self, connection_id: int, question: str, limit: int = 4, exclude_id: int | None = None
    ) -> list[Example]:
        """Trusted past question/SQL pairs on this connection most similar to ``question``."""
        if limit <= 0:
            return []
        stmt = (
            select(QueryRecord)
            .where(QueryRecord.connection_id == connection_id, QueryRecord.question.is_not(None), self._trusted())
            .order_by(QueryRecord.created_at.desc())
            .limit(CANDIDATE_POOL)
        )
        if exclude_id is not None:
            stmt = stmt.where(QueryRecord.id != exclude_id)
        words = tokenize(question)
        seen: set[str] = set()
        scored: list[Example] = []
        for record in self.db.scalars(stmt):
            key = normalize_question(record.question)
            if key in seen:
                continue  # newest answer for a repeated question wins
            seen.add(key)
            sql = record.corrected_sql or record.executed_sql
            if not sql:
                continue
            score = similarity(words, record.question)
            if score >= MIN_SIMILARITY:
                scored.append(
                    Example(
                        question=record.question,
                        sql=sql,
                        source="corrected" if record.corrected_sql else "approved",
                        score=round(score, 3),
                        query_id=record.id,
                    )
                )
        scored.sort(key=lambda e: (-e.score, e.source != "corrected"))
        return scored[:limit]

    def get_query_suggestions(
        self, user_id: int, connection_id: int | None = None, partial_query: str = "", limit: int = 8
    ) -> list[str]:
        """Questions this user has asked successfully before, filtered by the text typed so far."""
        stmt = (
            select(QueryRecord.question, QueryRecord.rating)
            .where(
                QueryRecord.user_id == user_id,
                QueryRecord.question.is_not(None),
                QueryRecord.status == "success",
                or_(QueryRecord.rating.is_(None), QueryRecord.rating >= 0),
            )
            .order_by(QueryRecord.created_at.desc())
            .limit(CANDIDATE_POOL)
        )
        if connection_id is not None:
            stmt = stmt.where(QueryRecord.connection_id == connection_id)
        needle = partial_query.strip().lower()
        counts: Counter[str] = Counter()
        display: dict[str, str] = {}
        order: dict[str, int] = {}
        for position, (question, rating) in enumerate(self.db.execute(stmt)):
            if needle and needle not in question.lower():
                continue
            key = normalize_question(question)
            display.setdefault(key, question.strip())
            order.setdefault(key, position)
            counts[key] += 3 if rating == 1 else 1
        ranked = sorted(counts, key=lambda k: (-counts[k], order[k]))
        return [display[k] for k in ranked[:limit]]

    def record_feedback(
        self,
        record: QueryRecord,
        *,
        rating: int | None,
        comment: str | None = None,
        corrected_sql: str | None = None,
    ) -> QueryRecord:
        record.rating = rating if rating in (1, -1) else None
        if comment is not None:
            record.feedback_comment = comment.strip() or None
        if corrected_sql is not None:
            record.corrected_sql = corrected_sql.strip() or None
        record.feedback_at = utcnow()
        self.db.commit()
        return record
