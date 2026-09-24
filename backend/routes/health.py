"""
Health, readiness and public instance information.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.database import check_db

router = APIRouter()


@router.get("/health")
def health():
    """Liveness probe."""
    return {"status": "healthy", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@router.get("/ready")
def ready():
    """Readiness probe: the internal database must be reachable."""
    database_ok = check_db()
    body = {
        "status": "ready" if database_ok else "unavailable",
        "checks": {
            "database": "ok" if database_ok else "failed",
            "ai": "configured" if settings.ai_configured else "not configured",
        },
    }
    return JSONResponse(body, status_code=200 if database_ok else 503)


@router.get("/info")
def info():
    """Public settings the web UI needs before login."""
    return {
        "app": settings.APP_NAME,
        "description": settings.APP_DESCRIPTION,
        "version": settings.APP_VERSION,
        "ai_configured": settings.ai_configured,
        "ai_model": settings.AI_MODEL if settings.ai_configured else None,
        "allow_registration": settings.ALLOW_REGISTRATION,
        "max_rows": settings.QUERY_MAX_ROWS,
    }
