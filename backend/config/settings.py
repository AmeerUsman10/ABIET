import os
"""
ABIET Configuration Settings
"""

from pydantic import BaseSettings
from typing import List
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

class Settings(BaseSettings):
    # Application Settings
    APP_NAME: str = "ABIET - Database AI Assistant"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "Artificial Business Intelligence Enabled Tool"
    
    # Server Settings
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    
    # CORS Settings
    CORS_ORIGINS: List[str] = ["*"]
    
    # Database Settings
    DATABASE_URL: str = "sqlite:///./abiet.db"  # SQLite for internal database
    MSSQL_DATABASE_URL: str = os.getenv("MSSQL_DATABASE_URL", "mssql+pyodbc://sa:YourStrong!Passw0rd@mssql/master?driver=ODBC+Driver+17+for+SQL+Server")
    ORACLE_DATABASE_URL: str = os.getenv("ORACLE_DATABASE_URL", "")
    
    # AI Settings
    AI_MODEL: str = "gpt-3.5-turbo"
    AI_TEMPERATURE: float = 0.7
    AI_MAX_TOKENS: int = 2000
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Security Settings
    SECRET_KEY: str = "your-secret-key-here"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

# Database session setup
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
