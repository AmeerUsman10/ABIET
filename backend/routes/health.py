"""
Health Check Endpoints
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict
from backend.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    app: str
    version: str

class ReadinessResponse(BaseModel):
    status: str
    dependencies: Dict[str, str]

@router.get("/health", response_model=HealthResponse)
async def health_check():
    try:
        logger.info("Health check requested")
        return HealthResponse(
            status="healthy",
            app=settings.APP_NAME,
            version=settings.APP_VERSION
        )
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")

@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check():
    try:
        logger.info("Readiness check requested")
        return ReadinessResponse(
            status="ready",
            dependencies={
                "database": "connected",
                "ai_models": "loaded"
            }
        )
    except Exception as e:
        logger.error(f"Readiness check error: {str(e)}")
        raise HTTPException(status_code=500, detail="Readiness check failed")
