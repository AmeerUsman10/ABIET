"""
Learning System Routes
"""

from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def learning_root():
    return {"message": "Learning system endpoint - to be implemented"}
