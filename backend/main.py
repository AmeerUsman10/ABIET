"""
ABIET - Database AI Assistant
Main FastAPI application: REST API under /api/v1 and the web UI at /.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ai.llm import LLMError, LLMNotConfigured
from backend.config import settings
from backend.database import init_db
from backend.routes import api_router
from backend.services.connectors import ConnectorError, dispose_all

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("abiet")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    if not settings.ai_configured:
        logger.warning("OPENAI_API_KEY is not set: questions cannot be answered until it is configured")
    yield
    dispose_all()


app = FastAPI(
    title="ABIET - Database AI Assistant",
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    path = request.url.path
    if not path.startswith(("/api/", "/docs", "/redoc", "/openapi.json")):
        response.headers.setdefault("Content-Security-Policy", _CSP)
        response.headers.setdefault("X-Frame-Options", "DENY")
    return response


@app.exception_handler(LLMNotConfigured)
async def _llm_not_configured(_request: Request, exc: LLMNotConfigured):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(LLMError)
async def _llm_error(_request: Request, exc: LLMError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(ConnectorError)
async def _connector_error(_request: Request, exc: ConnectorError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(api_router, prefix="/api/v1")

if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000)
