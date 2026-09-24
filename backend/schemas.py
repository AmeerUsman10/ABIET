"""
Request and response models for the REST API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from backend.services.connectors import DB_TYPES

DbTypeKey = Literal["mssql", "postgresql", "oracle", "mysql", "sqlite"]


def _check_password(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes")
    return value


# --- Auth ----------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    _pw = field_validator("password")(_check_password)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255, description="Username or email")
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=72)

    _pw = field_validator("new_password")(_check_password)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_admin: bool
    created_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# --- Connections -------------------------------------------------------------


def clean_options(db_type: str, options: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only the options defined for the database type, coerced to their declared types."""
    allowed = {o["key"]: o for o in DB_TYPES[db_type].options} if db_type in DB_TYPES else {}
    cleaned: dict[str, Any] = {}
    for key, value in (options or {}).items():
        spec = allowed.get(key)
        if spec is None or value is None:
            continue
        if spec["type"] == "bool":
            cleaned[key] = value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes", "on"}
        else:
            text = str(value).strip()[:500]
            if text:
                cleaned[key] = text
    return cleaned


class ConnectionBase(BaseModel):
    db_type: DbTypeKey
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, max_length=500)
    username: str | None = Field(default=None, max_length=255)
    options: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True

    @field_validator("host", "database", "username")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ConnectionCreate(ConnectionBase):
    name: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, max_length=1000)


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    db_type: DbTypeKey | None = None
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, max_length=500)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=1000, description="Omit to keep the stored password")
    clear_password: bool = False
    options: dict[str, Any] | None = None
    read_only: bool | None = None


class ConnectionTest(ConnectionBase):
    password: str | None = Field(default=None, max_length=1000)
    connection_id: int | None = Field(default=None, description="Use this saved connection's password if none given")


class ConnectionOut(BaseModel):
    id: int
    name: str
    db_type: str
    db_label: str
    host: str | None
    port: int | None
    database: str | None
    username: str | None
    has_password: bool
    options: dict[str, Any]
    read_only: bool
    is_demo: bool
    table_count: int | None
    schema_cached_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str
    server_version: str | None = None
    latency_ms: int | None = None


class DbTypeOut(BaseModel):
    key: str
    label: str
    default_port: int | None
    requires_host: bool
    options: list[dict[str, Any]]


# --- Queries -----------------------------------------------------------------


class AskRequest(BaseModel):
    connection_id: int
    question: str = Field(min_length=1, max_length=2000)
    parent_id: int | None = Field(default=None, description="Previous query id, for follow-up questions")
    execute: bool = True


class RunRequest(BaseModel):
    connection_id: int
    sql: str = Field(min_length=1, max_length=100_000)
    query_id: int | None = Field(default=None, description="Update this history entry instead of creating one")
    question: str | None = Field(default=None, max_length=2000)
    confirm_write: bool = False


class QueryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_id: int | None
    connection_name: str | None = None
    parent_id: int | None
    question: str | None
    generated_sql: str | None
    executed_sql: str | None
    explanation: str | None
    status: str
    error: str | None
    repaired: bool
    row_count: int | None
    duration_ms: int | None
    rating: int | None
    feedback_comment: str | None
    corrected_sql: str | None
    is_saved: bool
    title: str | None
    created_at: datetime


class ResultOut(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    affected_rows: int | None = None


class AskResponse(BaseModel):
    query: QueryOut
    result: ResultOut | None = None
    clarification: str | None = None
    requires_confirmation: bool = False
    chart: dict[str, Any] | None = None


class QueryList(BaseModel):
    items: list[QueryOut]
    total: int


class QueryUpdate(BaseModel):
    is_saved: bool | None = None
    title: str | None = Field(default=None, max_length=200)


class FeedbackRequest(BaseModel):
    rating: Literal[1, 0, -1] | None = Field(default=None, description="1 = correct, -1 = wrong, 0/null = clear")
    comment: str | None = Field(default=None, max_length=2000)
    corrected_sql: str | None = Field(default=None, max_length=100_000)


class LearnedExample(BaseModel):
    query_id: int | None
    question: str
    sql: str
    source: str


class InsightsOut(BaseModel):
    analysis: dict[str, Any]
    suggestions: list[str]


class AIInsightsOut(BaseModel):
    summary: str
    recommendations: list[str]
