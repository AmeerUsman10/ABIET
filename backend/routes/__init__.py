"""
ABIET API Routes
"""

from fastapi import APIRouter
from . import health, query, learning

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(query.router, prefix="/query", tags=["query"])
api_router.include_router(learning.router, prefix="/learning", tags=["learning"])
# Include the new DB router
from .db import router as db_router
api_router.include_router(db_router, prefix="/db")
# Include the auth router
from .auth import router as auth_router
api_router.include_router(auth_router, prefix="/auth")
