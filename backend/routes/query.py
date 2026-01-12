"""backend.routes.query
--------------------------------
FastAPI route for natural language query processing.
Now returns parsed tokens and generated SQL.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict

from ai.nlp.query_processor import processor

logger = logging.getLogger(__name__)
router = APIRouter()

class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    """Response model for the query endpoint."""

    status: str
    data: Dict


@router.post("/process", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    try:
        logger.info(f"Processing query: {request.query[:50]}...")
        result = processor.process(request.query)
        logger.info("Query processed successfully")
        return QueryResponse(status="success", data=result)
    except Exception as exc:  # pragma: no cover – defensive programming
        logger.error(f"Error processing query: {str(exc)}")
        raise HTTPException(status_code=500, detail="Failed to process the query. Please check your input and try again.")
