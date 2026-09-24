"""
ABIET configuration.

All settings can be overridden with environment variables or a ``.env`` file
in the working directory. See ``.env.example`` for the documented set.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_NAME: str = "ABIET"
    APP_DESCRIPTION: str = (
        "Artificial Business Intelligence Enabled Tool - ask your databases questions in plain English"
    )
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"

    # Storage. DATA_DIR holds the internal SQLite store (when DATABASE_URL is
    # unset), the generated secret key, and the demo database.
    DATA_DIR: Path = Path("data")
    DATABASE_URL: str | None = None

    # Security
    SECRET_KEY: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    ALLOW_REGISTRATION: bool = True
    CORS_ORIGINS: list[str] = []

    # AI (OpenAI or any OpenAI-compatible endpoint)
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None
    AI_MODEL: str = "gpt-4o-mini"
    AI_TEMPERATURE: float | None = 0.0
    AI_JSON_MODE: bool = True
    AI_TIMEOUT_SECONDS: float = 60.0
    AI_MAX_REPAIR_ATTEMPTS: int = 1
    AI_RATE_LIMIT_PER_MINUTE: int = 30
    AI_SCHEMA_CHAR_BUDGET: int = 12000
    AI_FEW_SHOT_EXAMPLES: int = 4
    AI_FOLLOW_UP_DEPTH: int = 3

    # Query execution
    QUERY_MAX_ROWS: int = 1000
    EXPORT_MAX_ROWS: int = 50000
    QUERY_TIMEOUT_SECONDS: int = 30
    CONNECT_TIMEOUT_SECONDS: int = 10
    SCHEMA_MAX_TABLES: int = 500

    # Database drivers
    MSSQL_ODBC_DRIVER: str = "ODBC Driver 18 for SQL Server"

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"sqlite:///{(self.DATA_DIR / 'abiet.db').resolve()}"

    @property
    def sqlite_dir(self) -> Path:
        """Only SQLite files inside this directory may be registered as connections."""
        return (self.DATA_DIR / "databases").resolve()

    @property
    def ai_configured(self) -> bool:
        return bool(self.OPENAI_API_KEY or self.OPENAI_BASE_URL)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
