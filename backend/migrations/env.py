"""Alembic environment for ABIET's internal database."""

from __future__ import annotations

from alembic import context

from backend.models import Base

target_metadata = Base.metadata


def run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    from backend.database import engine

    with engine.begin() as conn:
        run_migrations(conn)
