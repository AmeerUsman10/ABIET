"""
ABIET Configuration Settings
Updated for Pydantic v2 compatibility
"""

from pydantic_settings import BaseSettings
from typing import List

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
    DATABASE_URL: str = "sqlite:///./abiet.db"
    
    # AI Settings
    AI_MODEL: str = "gpt-3.5-turbo"
    AI_TEMPERATURE: float = 0.7
    AI_MAX_TOKENS: int = 2000
    
    # Security Settings
    SECRET_KEY: str = "your-secret-key-here"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
