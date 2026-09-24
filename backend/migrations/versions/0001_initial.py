"""Initial schema: users, saved database connections, query history.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())

    if "users" in existing:
        # Upgrading from ABIET 0.1, whose `users` table was created without migrations.
        columns = {c["name"] for c in inspector.get_columns("users")}
        with op.batch_alter_table("users") as batch:
            if "is_admin" not in columns:
                batch.add_column(sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
            if "is_active" not in columns:
                batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    else:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(50), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("hashed_password", sa.String(255), nullable=False),
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_users_username", "users", ["username"], unique=True)
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "db_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("db_type", sa.String(20), nullable=False),
        sa.Column("host", sa.String(255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("database", sa.String(500), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schema_cache", sa.JSON(), nullable=True),
        sa.Column("schema_cached_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("owner_id", "name", name="uq_db_connections_owner_name"),
    )
    op.create_index("ix_db_connections_owner_id", "db_connections", ["owner_id"])

    op.create_table(
        "query_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "connection_id", sa.Integer(), sa.ForeignKey("db_connections.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("query_history.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("generated_sql", sa.Text(), nullable=True),
        sa.Column("executed_sql", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("repaired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("feedback_comment", sa.Text(), nullable=True),
        sa.Column("corrected_sql", sa.Text(), nullable=True),
        sa.Column("feedback_at", sa.DateTime(), nullable=True),
        sa.Column("is_saved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_query_history_user_id", "query_history", ["user_id"])
    op.create_index("ix_query_history_connection_id", "query_history", ["connection_id"])
    op.create_index("ix_query_history_status", "query_history", ["status"])
    op.create_index("ix_query_history_is_saved", "query_history", ["is_saved"])
    op.create_index("ix_query_history_created_at", "query_history", ["created_at"])


def downgrade() -> None:
    op.drop_table("query_history")
    op.drop_table("db_connections")
    op.drop_table("users")
