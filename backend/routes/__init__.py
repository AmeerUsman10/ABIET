"""
ABIET API routes, mounted under /api/v1.
"""

from fastapi import APIRouter

from . import auth, connections, health, history, learning, query

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(connections.router, prefix="/connections", tags=["connections"])
api_router.include_router(query.router, prefix="/query", tags=["query"])
api_router.include_router(history.router, prefix="/queries", tags=["history"])
api_router.include_router(learning.router, prefix="/learning", tags=["learning"])
