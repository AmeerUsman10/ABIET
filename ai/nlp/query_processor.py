"""ai.nlp.query_processor
================================
This module provides a **very lightweight** skeleton for the query processing
component of the ABIET project. The full implementation will eventually
perform natural‑language parsing, intent detection, and translation to SQL.

For now we implement a minimal, testable API that can be expanded later:

* ``QueryProcessor`` – a class that holds configuration and exposes a
  ``process`` method.
* ``process`` – accepts a raw query string and returns a dictionary with the
  original query and a placeholder ``parsed`` field. The placeholder mimics the
  structure the final system will return (e.g. intent, entities, generated SQL).

The implementation deliberately avoids heavy NLP dependencies to keep the
container lightweight. When the project moves forward, developers can replace
the stub with a proper model (spaCy, transformers, etc.) without changing the
public interface.
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
    """Simple query processor placeholder.

    Attributes
    ----------
    language: str
        Language of the incoming queries. Defaults to ``"en"``.
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

    def process(self, query: str) -> Dict[str, Any]:
        """Process a raw query string.

        Parameters
        ----------
        query: str
            The user‑provided natural language query.

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
        }

# Export a singleton for convenient import in the FastAPI route.
processor = QueryProcessor()
