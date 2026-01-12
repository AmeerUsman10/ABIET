"""
Query Processing Routes
"""

from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def query_root():
    return {"message": "Query processing endpoint - to be implemented"}
