"""backend.routes.query
--------------------------------
FastAPI route for natural language query processing.
Now returns parsed tokens and generated SQL.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict

from backend.routes.db import DBConnection, _get_engine
from sqlalchemy import text
from backend.routes.auth import get_current_user
from backend.models import User

class QueryRequest(BaseModel):
    query: str
    connection: DBConnection


class QueryResponse(BaseModel):
    """Response model for the query endpoint."""

    status: str
    data: Dict


@router.post("/process", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest, current_user: User = Depends(get_current_user)):
    try:
        logger.info(f"Processing query for user {current_user.username}: {request.query[:50]}...")
        
        # Process natural language to SQL
        result = processor.process(request.query)
        generated_sql = result.get("generated_sql")
        
        if not generated_sql:
            return QueryResponse(status="error", data={"message": "Could not generate SQL from query"})
        
        # Execute the SQL on the provided connection
        engine = _get_engine(request.connection.type, request.connection)
        
        with engine.connect() as conn:
            sql_result = conn.execute(text(generated_sql))
            rows = [dict(row) for row in sql_result]
        
        result["rows"] = rows
        logger.info("Query processed and executed successfully")
        return QueryResponse(status="success", data=result)
    
    except Exception as exc:
        logger.error(f"Error processing/executing query: {str(exc)}")
        raise HTTPException(status_code=500, detail=f"Failed to process the query: {str(exc)}")
