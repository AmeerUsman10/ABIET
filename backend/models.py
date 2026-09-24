"""
ORM models for ABIET's internal database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    connections: Mapped[list[DatabaseConnection]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )


class DatabaseConnection(Base):
    """A database a user has registered for querying. The password is stored encrypted."""

    __tablename__ = "db_connections"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_db_connections_owner_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    db_type: Mapped[str] = mapped_column(String(20))
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    database: Mapped[str | None] = mapped_column(String(500), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    read_only: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    schema_cache: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    schema_cached_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="connections")


class QueryRecord(Base):
    """
    One question (or hand-written SQL) run against a connection, plus the
    feedback it received. Approved and corrected records become the examples
    the learning engine feeds back into future prompts.
    """

    __tablename__ = "query_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("db_connections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("query_history.id", ondelete="SET NULL"), nullable=True)

    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="generated", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    repaired: Mapped[bool] = mapped_column(Boolean, default=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    connection: Mapped[DatabaseConnection | None] = relationship()
