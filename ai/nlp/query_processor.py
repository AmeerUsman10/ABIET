"""ai.nlp.query_processor
================================
This module provides a lightweight NLP query processor for the ABIET project.
It tokenizes queries and generates basic SQL for simple SELECT statements.

For now, it supports patterns like:
- "select all customers" -> "SELECT * FROM customers"
- "show me users" -> "SELECT * FROM users"
- "get customer names" -> "SELECT names FROM customers" (basic)

Future versions will use advanced NLP models for complex queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import re


@dataclass
class QueryProcessor:
    """Simple query processor with basic SQL generation.

    Attributes
    ----------
    language: str
        Language of the incoming queries. Defaults to "en".
    """

    language: str = "en"

    def _basic_parse(self, query: str) -> Dict[str, Any]:
        """Parse query into tokens and basic structure."""
        tokens = query.strip().lower().split()
        return {
            "tokens": tokens,
            "token_count": len(tokens),
        }

    def _generate_sql(self, parsed: Dict[str, Any]) -> str:
        """Generate basic SQL from parsed tokens.

        Supports simple patterns:
        - select [all|*] [table]
        - show [me] [table]
        - get [column] from [table]
        """
        tokens = parsed["tokens"]
        if not tokens:
            return "-- Unable to parse query"

        # Pattern 1: select all [table]
        if tokens[0] == "select" and "all" in tokens:
            table_idx = tokens.index("all") + 1
            if table_idx < len(tokens):
                table = tokens[table_idx]
                return f"SELECT * FROM {table};"

        # Pattern 2: show [me] [table]
        if tokens[0] == "show":
            table = tokens[-1] if len(tokens) > 1 else "unknown"
            return f"SELECT * FROM {table};"

        # Pattern 3: get [column] from [table]
        if tokens[0] == "get" and "from" in tokens:
            from_idx = tokens.index("from")
            column = " ".join(tokens[1:from_idx])
            table = tokens[from_idx + 1] if from_idx + 1 < len(tokens) else "unknown"
            return f"SELECT {column} FROM {table};"

        # Fallback
        return "-- Query not recognized. Supported: 'select all customers', 'show users', 'get names from customers'"

    def process(self, query: str) -> Dict[str, Any]:
        """Process a raw query string.

        Returns
        -------
        dict
            Contains original query, parsed tokens, and generated SQL.
        """
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        parsed = self._basic_parse(query)
        sql = self._generate_sql(parsed)
        return {
            "original": query,
            "parsed": parsed,
            "generated_sql": sql,
        }

# Singleton processor
processor = QueryProcessor()
