"""backend.routes.query
--------------------------------
FastAPI route that exposes the query processing endpoint.
It now uses the ``ai.nlp.query_processor`` module introduced in the previous
patch. The endpoint accepts a JSON payload with a ``query`` field and returns the
structured result from the processor.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict

from ai.nlp.query_processor import processor

logger = logging.getLogger(__name__)
router = APIRouter()


class QueryRequest(BaseModel):
    """Request model for the query endpoint."""

    query: str


class QueryResponse(BaseModel):
    """Response model for the query endpoint."""

    status: str
    data: Dict


@router.post("/process", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """Process a natural‑language query and return a parsed representation.

    The current implementation is a stub that tokenises the input. Future
    versions will replace ``processor.process`` with full NLP and SQL generation.
    """
    try:
        logger.info(f"Processing query: {request.query[:50]}...")
        result = processor.process(request.query)
        logger.info("Query processed successfully")
        return QueryResponse(status="success", data=result)
    except Exception as exc:  # pragma: no cover – defensive programming
        logger.error(f"Error processing query: {str(exc)}")
        raise HTTPException(status_code=500, detail="Failed to process the query. Please check your input and try again.")
