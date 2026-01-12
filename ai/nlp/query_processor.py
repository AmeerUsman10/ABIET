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
import json
import openai
from backend.config.settings import settings
from ai.learning.learning_engine import LearningEngine


@dataclass
class QueryProcessor:
    """Simple query processor with basic SQL generation.

    Attributes
    ----------
    language: str
        Language of the incoming queries. Defaults to "en".
    """

    language: str = "en"

    def __post_init__(self):
        openai.api_key = settings.OPENAI_API_KEY
        self.learning_engine = LearningEngine()

    def _process_with_openai(self, query: str) -> Dict[str, Any]:
        """Process the query using OpenAI API for intent detection and SQL generation."""
        prompt = f"""
Convert the following natural language query to SQL. Assume a database with tables like users, orders, products, etc. Detect the intent and generate appropriate SQL.

Query: {query}

Return a JSON object with the following keys:
- "intent": a brief description of the intent (e.g., "retrieve user information")
- "sql": the generated SQL query
- "entities": any extracted entities (e.g., names, dates) as a list or dict

If unable to generate SQL, set "sql" to null and provide a reason in "error".
"""
        try:
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.AI_TEMPERATURE,
                max_tokens=settings.AI_MAX_TOKENS,
            )
            content = response.choices[0].message.content.strip()
            parsed = json.loads(content)
            return parsed
        except openai.OpenAIError as e:
            return {"intent": "error", "sql": None, "entities": {}, "error": str(e)}
        except json.JSONDecodeError as e:
            return {"intent": "error", "sql": None, "entities": {}, "error": f"Invalid JSON response: {str(e)}"}
        except Exception as e:
            return {"intent": "error", "sql": None, "entities": {}, "error": str(e)}

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
            A dictionary containing the original query and a ``parsed`` field
            with the result of the OpenAI processing.
        """
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        parsed = self._process_with_openai(query)
        
        # Record the interaction
        success = parsed.get("sql") is not None
        error = parsed.get("error") if not success else None
        self.learning_engine.record_interaction(
            natural_query=query,
            generated_sql=parsed.get("sql"),
            success=success,
            error=error
        )
        
        return {
            "original": query,
            "parsed": parsed,
            "generated_sql": parsed.get("sql"),
        }

# Singleton processor
processor = QueryProcessor()
