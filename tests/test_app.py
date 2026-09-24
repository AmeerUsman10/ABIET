import sqlite3

from alembic import command
from sqlalchemy import create_engine, inspect, text

from backend.database import alembic_config


def test_health_ready_and_info(client):
    assert client.get("/api/v1/health").json()["status"] == "healthy"
    ready = client.get("/api/v1/ready").json()
    assert ready["status"] == "ready" and ready["checks"]["database"] == "ok"
    info = client.get("/api/v1/info").json()
    assert info["app"] == "ABIET" and info["ai_configured"] is False and info["max_rows"] == 1000


def test_web_ui_is_served_with_security_headers(client):
    page = client.get("/")
    assert page.status_code == 200
    assert '<script type="module" src="js/app.js">' in page.text
    csp = page.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["x-content-type-options"] == "nosniff"
    for asset in ("/js/app.js", "/js/chart.js", "/js/views/ask.js", "/css/app.css", "/favicon.svg"):
        assert client.get(asset).status_code == 200, asset
    api = client.get("/api/v1/health")
    assert "content-security-policy" not in api.headers
    assert client.get("/docs").status_code == 200


def test_migrations_create_the_schema(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    assert {"users", "db_connections", "query_history", "alembic_version"} <= set(inspect(engine).get_table_names())


def test_migrations_upgrade_an_abiet_0_1_database(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50), email VARCHAR(100), "
            "hashed_password VARCHAR(100), created_at DATETIME, updated_at DATETIME)"
        )
        db.execute("INSERT INTO users (id, username, email, hashed_password) VALUES (1, 'old', 'o@x.com', 'h')")
        db.execute("CREATE TABLE queries (id INTEGER PRIMARY KEY, user_id INTEGER, query_text TEXT)")
    engine = create_engine(f"sqlite:///{path}")
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT username, is_admin, is_active FROM users")).one()
    assert tuple(row) == ("old", 0, 1)
    assert "query_history" in inspect(engine).get_table_names()


def test_models_match_migrations(tmp_path):
    """Fails when a model changes without a matching Alembic migration."""
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from backend.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'check.db'}")
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []
