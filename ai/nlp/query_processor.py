"""ai.nlp.query_processor
========================
Turns a natural-language question into SQL using a language model.

The processor is schema-aware (it sends the relevant tables and columns of the
connected database), dialect-aware, learns from past approved/corrected
queries (few-shot examples supplied by the learning engine), supports
follow-up questions, and can repair a query using the database's error
message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ai.llm import LLMClient
from ai.nlp.prompts import Example, Turn, build_messages, build_repair_messages

CHART_TYPES = {"bar", "line", "pie"}
_SQL_FENCE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE)


@dataclass
class GenerationResult:
    sql: str | None
    explanation: str | None
    clarification: str | None = None
    chart: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none"}:
        return None
    return text


def parse_generation(raw: dict[str, Any]) -> GenerationResult:
    sql = _clean_text(raw.get("sql") or raw.get("query"))
    if sql:
        sql = _SQL_FENCE.sub("", sql).strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        sql = sql or None
    chart = raw.get("chart")
    if isinstance(chart, dict) and chart.get("type") in CHART_TYPES:
        y = chart.get("y")
        if isinstance(y, str):
            y = [y]
        chart = {"type": chart["type"], "x": chart.get("x"), "y": [str(c) for c in (y or [])]}
    else:
        chart = None
    clarification = _clean_text(raw.get("clarification"))
    return GenerationResult(
        sql=sql,
        explanation=_clean_text(raw.get("explanation")),
        clarification=clarification if not sql else None,
        chart=chart,
        raw=raw,
    )


class QueryProcessor:
    def __init__(self, llm: LLMClient, *, max_rows: int = 1000, schema_budget: int = 12000):
        self.llm = llm
        self.max_rows = max_rows
        self.schema_budget = schema_budget
        self.last_messages: list[dict[str, str]] = []

    def _messages(
        self,
        question: str,
        *,
        db_type: str,
        schema: dict[str, Any],
        examples: list[Example] | None = None,
        history: list[Turn] | None = None,
        allow_writes: bool = False,
    ) -> list[dict[str, str]]:
        return build_messages(
            question=question,
            db_type=db_type,
            schema=schema,
            examples=examples or [],
            history=history or [],
            max_rows=self.max_rows,
            schema_budget=self.schema_budget,
            allow_writes=allow_writes,
        )

    def generate(self, question: str, **context: Any) -> GenerationResult:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        messages = self._messages(question.strip(), **context)
        self.last_messages = messages
        result = parse_generation(self.llm.complete_json(messages))
        if not result.sql and not result.clarification:
            result.clarification = "I couldn't turn that into a query. Could you rephrase or add more detail?"
        return result

    def repair(self, question: str, failed_sql: str, error: str, **context: Any) -> GenerationResult:
        messages = build_repair_messages(self._messages(question.strip(), **context), failed_sql, error)
        self.last_messages = messages
        return parse_generation(self.llm.complete_json(messages))
