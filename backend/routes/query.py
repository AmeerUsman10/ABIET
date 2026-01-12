"""backend.routes.query
--------------------------------
FastAPI route for natural language query processing.
Now returns parsed tokens and generated SQL.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai.nlp.query_processor import processor

router = APIRouter()

class QueryRequest(BaseModel):
    query: str

@router.post("/")
async def query_endpoint(request: QueryRequest):
    try:
        result = processor.process(request.query)
        return {"status": "success", "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
