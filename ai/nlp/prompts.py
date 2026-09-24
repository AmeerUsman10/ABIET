"""
Prompt construction for natural-language-to-SQL generation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from ai.learning.similarity import tokenize

DB_LABELS = {
    "mssql": "Microsoft SQL Server",
    "postgresql": "PostgreSQL",
    "oracle": "Oracle Database",
    "mysql": "MySQL",
    "sqlite": "SQLite",
}

DIALECT_RULES = {
    "mssql": [
        "Use T-SQL. Limit rows with TOP n (or OFFSET ... FETCH NEXT n ROWS ONLY after ORDER BY); LIMIT does not exist.",
        "Dates: GETDATE(), DATEADD, DATEDIFF, YEAR(), MONTH(), DATEFROMPARTS, FORMAT(date, 'yyyy-MM').",
        "Quote identifiers that contain spaces or reserved words with [square brackets].",
        "ORDER BY is not allowed inside views, derived tables or CTEs unless TOP is used.",
    ],
    "postgresql": [
        "Use PostgreSQL syntax. Limit rows with LIMIT n.",
        "Dates: NOW(), CURRENT_DATE, date_trunc('month', col), EXTRACT(YEAR FROM col), col - INTERVAL '30 days'.",
        "Use ILIKE for case-insensitive text matching.",
        "Identifiers shown in double quotes must stay double-quoted (they are case-sensitive).",
        "Cast before ROUND on double precision values: ROUND(x::numeric, 2).",
    ],
    "oracle": [
        "Use Oracle SQL. Limit rows with FETCH FIRST n ROWS ONLY; LIMIT does not exist.",
        "Dates: SYSDATE, TRUNC(col, 'MM'), ADD_MONTHS, EXTRACT(YEAR FROM col), TO_CHAR(col, 'YYYY-MM').",
        "Do not use AS before table aliases. Use FROM DUAL when no table is needed.",
    ],
    "mysql": [
        "Use MySQL syntax. Limit rows with LIMIT n.",
        "Dates: NOW(), CURDATE(), DATE_FORMAT(col, '%Y-%m'), DATE_SUB(CURDATE(), INTERVAL 30 DAY), YEAR(col).",
        "Quote identifiers that contain spaces or reserved words with `backticks`.",
    ],
    "sqlite": [
        "Use SQLite syntax. Limit rows with LIMIT n.",
        "Dates are stored as ISO-8601 text: use date('now'), date('now', '-30 days'), strftime('%Y-%m', col), "
        "strftime('%Y', col). Compare dates as text in YYYY-MM-DD form.",
        "Use ROUND(x, 2) for money and CAST(x AS REAL) before dividing integers.",
    ],
}

_RESERVED = frozenset(
    """user order group select table from where limit key desc asc check column index end to as in is on or and
    not all any case when then else default primary foreign references unique grant both cast union offset fetch
    window rows level date number size uid file mode access audit current session comment type value values""".split()
)
_SIMPLE_LOWER = re.compile(r"^[a-z_][a-z0-9_$]*$")
_SIMPLE_ANY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(name: str, db_type: str) -> str:
    if db_type in ("postgresql", "oracle"):
        safe = bool(_SIMPLE_LOWER.match(name))
    else:
        safe = bool(_SIMPLE_ANY.match(name))
    if safe and name.lower() not in _RESERVED:
        return name
    if db_type == "mssql":
        return "[" + name.replace("]", "]]") + "]"
    if db_type == "mysql":
        return "`" + name.replace("`", "``") + "`"
    return '"' + name.replace('"', '""') + '"'


def table_ref(table: dict[str, Any], db_type: str) -> str:
    name = quote_ident(table["name"], db_type)
    if table.get("schema"):
        return f"{quote_ident(table['schema'], db_type)}.{name}"
    return name


def _render_table(table: dict[str, Any], db_type: str) -> str:
    fk_map: dict[str, str] = {}
    for fk in table.get("foreign_keys") or []:
        target = {"name": fk["referred_table"], "schema": fk.get("referred_schema")}
        for col, ref_col in zip(fk["columns"], fk["referred_columns"], strict=False):
            fk_map[col] = f"{table_ref(target, db_type)}.{quote_ident(ref_col, db_type)}"
    kind = " (view)" if table.get("kind") == "view" else ""
    lines = [f"TABLE {table_ref(table, db_type)}{kind}"]
    for col in table.get("columns") or []:
        parts = [f"  {quote_ident(col['name'], db_type)} {col['type']}"]
        if col.get("primary_key"):
            parts.append("PK")
        if col["name"] in fk_map:
            parts.append(f"-> {fk_map[col['name']]}")
        if col.get("values"):
            parts.append("values: " + ", ".join("'" + str(v).replace("'", "''") + "'" for v in col["values"]))
        if col.get("comment"):
            parts.append(f"-- {col['comment']}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def rank_tables(tables: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    """Order tables by relevance to the question; foreign-key neighbours of relevant tables get a boost."""
    words = set(tokenize(question))
    scores: dict[int, float] = {}
    by_name: dict[str, int] = {}
    for idx, table in enumerate(tables):
        by_name[table["name"].lower()] = idx
        score = 3.0 * len(words & set(tokenize(table["name"])))
        for col in table.get("columns") or []:
            score += 1.0 * len(words & set(tokenize(col["name"])))
            for value in col.get("values") or []:
                if set(tokenize(str(value))) & words:
                    score += 2.0
        scores[idx] = score
    boosted = dict(scores)
    for idx, table in enumerate(tables):
        if scores[idx] <= 0:
            continue
        for fk in table.get("foreign_keys") or []:
            target = by_name.get(fk["referred_table"].lower())
            if target is not None:
                boosted[target] += 1.0 + scores[idx] * 0.25
    order = sorted(range(len(tables)), key=lambda i: (-boosted[i], i))
    return [tables[i] for i in order]


def render_schema(schema: dict[str, Any], question: str, db_type: str, budget: int) -> str:
    tables = schema.get("tables") or []
    if not tables:
        return "(no tables found)"
    rendered = [_render_table(t, db_type) for t in tables]
    if sum(len(r) + 2 for r in rendered) <= budget:
        return "\n\n".join(rendered)

    parts: list[str] = []
    used = 0
    omitted: list[str] = []
    for table in rank_tables(tables, question):
        text = _render_table(table, db_type)
        if used + len(text) + 2 <= budget:
            parts.append(text)
            used += len(text) + 2
        else:
            omitted.append(table_ref(table, db_type))
    if omitted:
        listing = ", ".join(omitted)
        if len(listing) > 2000:
            listing = listing[:2000] + ", ..."
        parts.append(f"Other tables (columns not shown): {listing}")
    return "\n\n".join(parts)


@dataclass
class Example:
    question: str
    sql: str
    source: str = "approved"
    score: float = 0.0
    query_id: int | None = None


@dataclass
class Turn:
    question: str
    sql: str | None
    explanation: str | None = None


RESPONSE_FORMAT = (
    '{"sql": "<one SQL query, or null>", '
    '"explanation": "<one or two plain-English sentences describing what the result shows>", '
    '"clarification": "<a short question for the user if the request is ambiguous, otherwise null>", '
    '"chart": {"type": "bar|line|pie|none", "x": "<label column>", "y": ["<numeric column>"]}}'
)


def build_system_prompt(
    *,
    db_type: str,
    schema_text: str,
    examples: list[Example],
    max_rows: int,
    allow_writes: bool,
    today: date | None = None,
) -> str:
    rules = [
        "Use only tables and columns that appear in the schema below, spelled and quoted exactly as shown.",
        "Join tables using the foreign keys (->) shown in the schema.",
        (
            "Write a single SELECT statement (CTEs are fine). Only write INSERT/UPDATE/DELETE if the user "
            "explicitly asks to change data."
            if allow_writes
            else "Write a single read-only SELECT statement (CTEs are fine). This connection is read-only: "
            "never write INSERT, UPDATE, DELETE, DDL or procedure calls."
        ),
        "Do not end the query with a semicolon.",
        "Give computed columns short, readable aliases (e.g. total_revenue, order_count).",
        "For top/most/least questions, sort and limit the result. Otherwise do not add an arbitrary row limit "
        f"(results are capped at {max_rows} rows automatically).",
        "When a column lists sample values, filter with those exact values.",
        "For trends over time, group by a period (month, quarter, year) and order chronologically.",
        "If the question is ambiguous or cannot be answered from this schema, set sql to null and ask a short "
        "clarifying question.",
        "Suggest a chart only when it helps: line for time series, bar for comparing categories, pie for shares "
        "of a whole with few categories; otherwise use type none.",
        *DIALECT_RULES.get(db_type, []),
    ]
    sections = [
        f"You are ABIET, an expert data analyst. You translate business questions into SQL for a "
        f"{DB_LABELS.get(db_type, db_type)} database.",
        f"Today's date is {(today or date.today()).isoformat()}.",
        "Rules:\n" + "\n".join(f"- {r}" for r in rules),
        "Respond only with a JSON object in this format:\n" + RESPONSE_FORMAT,
        "Database schema:\n" + schema_text,
    ]
    if examples:
        shots = "\n\n".join(f"Question: {e.question}\nSQL: {e.sql}" for e in examples)
        sections.append(
            "Questions previously answered correctly on this database (users approved or corrected these; "
            "follow the same conventions):\n" + shots
        )
    return "\n\n".join(sections)


def build_messages(
    *,
    question: str,
    db_type: str,
    schema: dict[str, Any],
    examples: list[Example],
    history: list[Turn],
    max_rows: int,
    schema_budget: int,
    allow_writes: bool = False,
    today: date | None = None,
) -> list[dict[str, str]]:
    context = " ".join([*(t.question for t in history), question])
    system = build_system_prompt(
        db_type=db_type,
        schema_text=render_schema(schema, context, db_type, schema_budget),
        examples=examples,
        max_rows=max_rows,
        allow_writes=allow_writes,
        today=today,
    )
    messages = [{"role": "system", "content": system}]
    for turn in history:
        messages.append({"role": "user", "content": turn.question})
        messages.append(
            {"role": "assistant", "content": json.dumps({"sql": turn.sql, "explanation": turn.explanation})}
        )
    messages.append({"role": "user", "content": question})
    return messages


def build_repair_messages(messages: list[dict[str, str]], failed_sql: str, error: str) -> list[dict[str, str]]:
    return [
        *messages,
        {"role": "assistant", "content": json.dumps({"sql": failed_sql})},
        {
            "role": "user",
            "content": "Running that query failed with this database error:\n"
            f"{error[:1500]}\n\n"
            "Fix the query so it runs on this database and still answers my question. "
            "Respond with the same JSON format.",
        },
    ]
