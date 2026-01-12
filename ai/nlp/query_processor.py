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


@dataclass
class QueryProcessor:
    """Simple query processor placeholder.

    Attributes
    ----------
    language: str
        Language of the incoming queries. Defaults to ``"en"``.
    """

    language: str = "en"

    def _basic_parse(self, query: str) -> Dict[str, Any]:
        """Very naive parsing – split on whitespace and return tokens.

        This method exists solely to demonstrate a deterministic output that
        can be unit‑tested. Real logic will replace this implementation.
        """
        tokens = query.strip().split()
        return {
            "tokens": tokens,
            "token_count": len(tokens),
        }

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
            with the result of the placeholder parser.
        """
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        parsed = self._basic_parse(query)
        return {
            "original": query,
            "parsed": parsed,
        }

# Export a singleton for convenient import in the FastAPI route.
processor = QueryProcessor()
