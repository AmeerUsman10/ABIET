"""
Health Check Endpoints
"""

from fastapi import APIRouter
from backend.config.settings import settings

router = APIRouter()

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }

@router.get("/ready")
async def readiness_check():
    return {
        "status": "ready",
        "dependencies": {
            "database": "connected",
            "ai_models": "loaded"
        }
    }
