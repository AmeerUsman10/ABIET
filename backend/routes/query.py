"""backend.routes.query
--------------------------------
FastAPI route that exposes the query processing endpoint.
It now uses the ``ai.nlp.query_processor`` module introduced in the previous
patch. The endpoint accepts a JSON payload with a ``query`` field and returns the
structured result from the processor.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai.nlp.query_processor import processor

router = APIRouter()


class QueryRequest(BaseModel):
    """Request model for the query endpoint."""

    query: str


@router.post("/api/v1/query/")
async def query_endpoint(request: QueryRequest):
    """Process a natural‑language query and return a parsed representation.

    The current implementation is a stub that tokenises the input. Future
    versions will replace ``processor.process`` with full NLP and SQL generation.
    """
    try:
        result = processor.process(request.query)
        return {"status": "success", "data": result}
    except Exception as exc:  # pragma: no cover – defensive programming
        raise HTTPException(status_code=500, detail=str(exc))
