"""
Internal application database (users, saved connections, query history).

This is ABIET's own store - not the databases users query. It defaults to a
SQLite file in ``DATA_DIR`` and can be pointed at PostgreSQL (or any
SQLAlchemy-supported database) with ``DATABASE_URL``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings

logger = logging.getLogger(__name__)

_url = settings.database_url
_is_sqlite = _url.startswith("sqlite")

if _is_sqlite:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _record):
        # SQLite ignores ON DELETE CASCADE / SET NULL unless this is enabled per connection.
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def init_db() -> None:
    """Bring the internal database schema up to date."""
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
    logger.info("Internal database ready")


def check_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - readiness probe must never raise
        logger.exception("Internal database check failed")
        return False
