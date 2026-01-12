"""
ABIET API Routes
"""

from fastapi import APIRouter
from backend.routes import health, query, learning

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(query.router, prefix="/query", tags=["query"])
api_router.include_router(learning.router, prefix="/learning", tags=["learning"])
