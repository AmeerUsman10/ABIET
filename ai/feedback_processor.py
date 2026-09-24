"""
ABIET Feedback Processor
========================
Analyzes query history and user feedback to measure how well the assistant
is doing and suggest improvements.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.learning.similarity import tokenize
from ai.llm import LLMClient
from backend.models import DatabaseConnection, QueryRecord, utcnow

_QUERY_FEATURES = {
    "join": re.compile(r"\bJOIN\b", re.IGNORECASE),
    "aggregate": re.compile(r"\b(GROUP\s+BY|COUNT|SUM|AVG|MIN|MAX)\b", re.IGNORECASE),
    "filter": re.compile(r"\bWHERE\b", re.IGNORECASE),
    "sort": re.compile(r"\bORDER\s+BY\b", re.IGNORECASE),
    "cte": re.compile(r"^\s*WITH\b", re.IGNORECASE),
    "window": re.compile(r"\bOVER\s*\(", re.IGNORECASE),
    "subquery": re.compile(r"\(\s*SELECT\b", re.IGNORECASE),
}
_FEEDBACK_THEMES = {
    "incorrect_results": ("wrong", "incorrect", "not right", "mistake", "error", "bad"),
    "missing_data": ("missing", "not found", "empty", "no data", "incomplete"),
    "performance": ("slow", "performance", "timeout", "took too long"),
    "formatting": ("format", "display", "column name", "decimal", "rounding"),
    "misunderstood": ("misunderstood", "not what i asked", "meant", "instead"),
}


def _error_signature(error: str) -> str:
    first = error.strip().splitlines()[0] if error.strip() else ""
    first = re.sub(r"'[^']*'|\"[^\"]*\"|\[[^\]]*\]", "…", first)
    first = re.sub(r"\d+", "N", first)
    return first[:140]


class FeedbackProcessor:
    def __init__(self, db: Session, llm: LLMClient | None = None):
        self.db = db
        self.llm = llm

    def _records(self, user_id: int | None, since: datetime | None = None) -> list[QueryRecord]:
        stmt = select(QueryRecord)
        if user_id is not None:
            stmt = stmt.where(QueryRecord.user_id == user_id)
        if since is not None:
            stmt = stmt.where(QueryRecord.created_at >= since)
        return list(self.db.scalars(stmt))

    def analyze_feedback_patterns(self, user_id: int | None = None, days: int = 30) -> dict[str, Any]:
        records = self._records(user_id)
        now = utcnow()
        since = now - timedelta(days=days)

        executed = [r for r in records if r.status in ("success", "error")]
        ai_questions = [r for r in records if r.question]
        success = sum(1 for r in records if r.status == "success")
        errors = sum(1 for r in records if r.status == "error")
        positive = sum(1 for r in records if r.rating == 1)
        negative = sum(1 for r in records if r.rating == -1)
        corrections = sum(1 for r in records if r.corrected_sql)
        durations = [r.duration_ms for r in records if r.status == "success" and r.duration_ms is not None]

        daily: dict[str, dict[str, int]] = {}
        for offset in range(days - 1, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            daily[day] = {"total": 0, "success": 0, "error": 0}
        for r in records:
            if r.created_at and r.created_at >= since:
                bucket = daily.get(r.created_at.date().isoformat())
                if bucket is not None:
                    bucket["total"] += 1
                    if r.status == "success":
                        bucket["success"] += 1
                    elif r.status == "error":
                        bucket["error"] += 1

        error_counts = Counter(_error_signature(r.error) for r in records if r.status == "error" and r.error)
        features: Counter[str] = Counter()
        for r in records:
            if r.status == "success" and r.executed_sql:
                for name, pattern in _QUERY_FEATURES.items():
                    if pattern.search(r.executed_sql):
                        features[name] += 1

        themes: Counter[str] = Counter()
        comment_words: Counter[str] = Counter()
        for r in records:
            if r.feedback_comment:
                text = r.feedback_comment.lower()
                matched = [t for t, keys in _FEEDBACK_THEMES.items() if any(k in text for k in keys)]
                themes.update(matched or ["other"])
                comment_words.update(w for w in tokenize(text) if len(w) > 2)

        by_connection: Counter[int] = Counter(r.connection_id for r in records if r.connection_id)
        names = {}
        if by_connection:
            rows = self.db.execute(
                select(DatabaseConnection.id, DatabaseConnection.name).where(
                    DatabaseConnection.id.in_(list(by_connection))
                )
            )
            names = dict(rows.all())

        negatives = sorted(
            (r for r in records if r.rating == -1 and r.question),
            key=lambda r: r.feedback_at or r.created_at,
            reverse=True,
        )[:10]

        rated = positive + negative
        return {
            "totals": {
                "queries": len(records),
                "ai_questions": len(ai_questions),
                "executed": len(executed),
                "success": success,
                "errors": errors,
                "blocked": sum(1 for r in records if r.status == "blocked"),
                "clarifications": sum(1 for r in records if r.status == "clarification"),
                "success_rate": round(success / len(executed), 3) if executed else None,
                "repaired": sum(1 for r in records if r.repaired),
                "avg_duration_ms": int(sum(durations) / len(durations)) if durations else None,
                "saved": sum(1 for r in records if r.is_saved),
            },
            "feedback": {
                "positive": positive,
                "negative": negative,
                "corrections": corrections,
                "approval_rate": round(positive / rated, 3) if rated else None,
                "themes": dict(themes.most_common()),
                "common_words": dict(comment_words.most_common(15)),
            },
            "daily": [{"date": d, **v} for d, v in daily.items()],
            "top_errors": [{"error": e, "count": c} for e, c in error_counts.most_common(5)],
            "query_features": dict(features.most_common()),
            "connections": [
                {"connection_id": cid, "name": names.get(cid, f"#{cid}"), "queries": n}
                for cid, n in by_connection.most_common(10)
            ],
            "recent_negative": [
                {
                    "id": r.id,
                    "question": r.question,
                    "comment": r.feedback_comment,
                    "sql": r.executed_sql or r.generated_sql,
                }
                for r in negatives
            ],
            "period_days": days,
            "generated_at": now.isoformat(),
        }

    def generate_improvement_suggestions(self, analysis: dict[str, Any]) -> list[str]:
        totals = analysis["totals"]
        feedback = analysis["feedback"]
        suggestions: list[str] = []

        if totals["queries"] == 0:
            return ["No queries yet. Ask a question to start building history the assistant can learn from."]
        if totals["success_rate"] is not None and totals["success_rate"] < 0.8 and totals["executed"] >= 5:
            suggestions.append(
                f"Only {totals['success_rate']:.0%} of queries ran successfully. Review the most common errors "
                "below; refreshing the schema after database changes often fixes 'invalid column/table' errors."
            )
        if any("column" in e["error"].lower() or "table" in e["error"].lower() for e in analysis["top_errors"]):
            suggestions.append(
                "Several errors mention unknown tables or columns. Refresh the schema for affected connections."
            )
        if feedback["negative"] > feedback["positive"] and feedback["negative"] >= 3:
            suggestions.append(
                "Negative feedback outweighs positive. Correct the SQL on thumbs-down answers: corrections are "
                "reused as examples for similar questions."
            )
        if feedback["positive"] + feedback["corrections"] < 5:
            suggestions.append(
                "Rate answers with thumbs up/down. Approved and corrected queries teach the assistant your "
                "database's conventions."
            )
        asked = totals["ai_questions"]
        if asked and totals["clarifications"] / asked > 0.2:
            suggestions.append(
                "Many questions needed clarification. Mention the metric, time period and grouping explicitly "
                "(e.g. 'monthly revenue by region in 2025')."
            )
        if totals["blocked"]:
            suggestions.append(
                f"{totals['blocked']} statement(s) were blocked by the read-only safety check. Enable writes on a "
                "connection only if you need to modify data."
            )
        if totals["repaired"]:
            suggestions.append(
                f"{totals['repaired']} quer{'y was' if totals['repaired'] == 1 else 'ies were'} automatically "
                "repaired after a database error."
            )
        if feedback["themes"].get("performance"):
            suggestions.append("Users reported slow queries. Consider indexes on frequently filtered columns.")
        if not suggestions:
            suggestions.append("The assistant is performing well. Keep rating answers to maintain accuracy.")
        return suggestions

    def get_ai_insights(self, analysis: dict[str, Any]) -> dict[str, Any]:
        if self.llm is None:
            raise ValueError("No language model available")
        compact = {k: v for k, v in analysis.items() if k != "daily"}
        messages = [
            {
                "role": "system",
                "content": "You analyze usage and feedback data from a natural-language-to-SQL assistant. "
                'Respond with JSON: {"summary": "<3-5 sentences>", "recommendations": ["<actionable item>", ...]}',
            },
            {"role": "user", "content": json.dumps(compact, default=str)[:12000]},
        ]
        raw = self.llm.complete_json(messages)
        recs = raw.get("recommendations") or []
        if not isinstance(recs, list):
            recs = [str(recs)]
        return {"summary": str(raw.get("summary") or ""), "recommendations": [str(r) for r in recs][:10]}

    def export_report(self, user_id: int | None = None, days: int = 30) -> dict[str, Any]:
        analysis = self.analyze_feedback_patterns(user_id=user_id, days=days)
        return {"analysis": analysis, "suggestions": self.generate_improvement_suggestions(analysis)}
