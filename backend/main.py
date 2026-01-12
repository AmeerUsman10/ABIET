"""
ABIET - Database AI Assistant
Main FastAPI Application
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routes import api_router
from backend.config.settings import settings, engine
from backend.models import Base
from sqlalchemy.orm import Session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ABIET - Database AI Assistant",
    description="Artificial Business Intelligence Enabled Tool",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Configuration - using settings instance
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Create database tables
Base.metadata.create_all(bind=engine)

@app.get("/")
async def root():
    return {
        "message": "ABIET - Database AI Assistant",
        "version": "0.1.0",
        "status": "under development"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.SERVER_HOST, port=settings.SERVER_PORT)
