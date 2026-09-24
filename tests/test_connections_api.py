import sqlite3

import pytest
from conftest import register

from backend.config import settings
from backend.database import SessionLocal
from backend.models import DatabaseConnection
from backend.security import decrypt_secret

POSTGRES = {
    "name": "Warehouse",
    "db_type": "postgresql",
    "host": "db.internal",
    "port": 5432,
    "database": "sales",
    "username": "reader",
    "password": "s3cr3t:@/!",
    "options": {"sslmode": "require", "schemas": "public, mart", "bogus": "dropped"},
}


@pytest.fixture
def writable_db():
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)
    path = settings.sqlite_dir / "scratch.sqlite"
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER)")
        db.executemany("INSERT INTO items (name, qty) VALUES (?, ?)", [("a", 1), ("b", 2), ("c", 3)])
    yield path.name
    path.unlink(missing_ok=True)


def test_types_describe_every_supported_database(client, auth):
    types = {t["key"]: t for t in client.get("/api/v1/connections/types", headers=auth).json()}
    assert set(types) == {"mssql", "postgresql", "oracle", "mysql", "sqlite"}
    assert types["mssql"]["default_port"] == 1433
    assert {o["key"] for o in types["mssql"]["options"]} >= {"instance", "trusted_connection", "driver"}
    assert types["sqlite"]["requires_host"] is False


def test_create_connection_encrypts_password_and_never_returns_it(client, auth):
    response = client.post("/api/v1/connections", headers=auth, json=POSTGRES)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["has_password"] is True
    assert "password" not in body and "password_encrypted" not in body
    assert body["options"] == {"sslmode": "require", "schemas": "public, mart"}
    assert body["read_only"] is True and body["db_label"] == "PostgreSQL"
    with SessionLocal() as db:
        stored = db.get(DatabaseConnection, body["id"])
        assert stored.password_encrypted != POSTGRES["password"]
        assert decrypt_secret(stored.password_encrypted) == POSTGRES["password"]
    listed = client.get("/api/v1/connections", headers=auth).json()
    assert [c["name"] for c in listed] == ["Warehouse"]


def test_connection_names_are_unique_per_user(client, auth):
    assert client.post("/api/v1/connections", headers=auth, json=POSTGRES).status_code == 201
    assert client.post("/api/v1/connections", headers=auth, json=POSTGRES).status_code == 409
    other = register(client, "bob")
    assert client.post("/api/v1/connections", headers=other, json=POSTGRES).status_code == 201


def test_invalid_connections_are_rejected(client, auth):
    missing_host = {**POSTGRES, "host": None}
    assert client.post("/api/v1/connections", headers=auth, json=missing_host).status_code == 422
    escape = {"name": "x", "db_type": "sqlite", "database": "../abiet.db"}
    response = client.post("/api/v1/connections", headers=auth, json=escape)
    assert response.status_code == 422 and "must be inside" in response.json()["detail"]
    unknown = {**POSTGRES, "db_type": "db2"}
    assert client.post("/api/v1/connections", headers=auth, json=unknown).status_code == 422


def test_users_cannot_see_each_others_connections(client, auth):
    conn_id = client.post("/api/v1/connections", headers=auth, json=POSTGRES).json()["id"]
    other = register(client, "mallory")
    assert client.get("/api/v1/connections", headers=other).json() == []
    for method, path in [
        ("get", f"/api/v1/connections/{conn_id}"),
        ("put", f"/api/v1/connections/{conn_id}"),
        ("delete", f"/api/v1/connections/{conn_id}"),
        ("post", f"/api/v1/connections/{conn_id}/test"),
        ("get", f"/api/v1/connections/{conn_id}/schema"),
    ]:
        kwargs = {"json": {"name": "stolen"}} if method == "put" else {}
        assert getattr(client, method)(path, headers=other, **kwargs).status_code == 404, path
    # nor borrow its stored password for a test
    test = client.post(
        "/api/v1/connections/test", headers=other, json={**POSTGRES, "password": None, "connection_id": conn_id}
    )
    assert test.status_code == 404


def test_update_keeps_or_replaces_the_password(client, auth):
    conn_id = client.post("/api/v1/connections", headers=auth, json=POSTGRES).json()["id"]
    renamed = client.put(f"/api/v1/connections/{conn_id}", headers=auth, json={"name": "DWH", "port": 6543})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "DWH" and renamed.json()["port"] == 6543
    with SessionLocal() as db:
        assert decrypt_secret(db.get(DatabaseConnection, conn_id).password_encrypted) == POSTGRES["password"]
    client.put(f"/api/v1/connections/{conn_id}", headers=auth, json={"password": "new-pw"})
    with SessionLocal() as db:
        assert decrypt_secret(db.get(DatabaseConnection, conn_id).password_encrypted) == "new-pw"
    cleared = client.put(f"/api/v1/connections/{conn_id}", headers=auth, json={"clear_password": True})
    assert cleared.json()["has_password"] is False


def test_delete_connection(client, auth):
    conn_id = client.post("/api/v1/connections", headers=auth, json=POSTGRES).json()["id"]
    assert client.delete(f"/api/v1/connections/{conn_id}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/connections/{conn_id}", headers=auth).status_code == 404


def test_test_endpoints(client, auth, demo):
    ok = client.post(f"/api/v1/connections/{demo}/test", headers=auth).json()
    assert ok["ok"] is True and ok["server_version"]
    unsaved = client.post(
        "/api/v1/connections/test",
        headers=auth,
        json={"db_type": "postgresql", "host": "127.0.0.1", "port": 1, "database": "x", "username": "u"},
    ).json()
    assert unsaved["ok"] is False and unsaved["message"]


def test_demo_connection_is_idempotent_and_read_only(client, auth, demo):
    again = client.post("/api/v1/connections/demo", headers=auth).json()
    assert again["id"] == demo and again["is_demo"] and again["read_only"]
    assert client.put(f"/api/v1/connections/{demo}", headers=auth, json={"read_only": False}).status_code == 400
    assert client.put(f"/api/v1/connections/{demo}", headers=auth, json={"name": "Sample"}).json()["name"] == "Sample"


def test_schema_is_cached_and_refreshable(client, auth, demo):
    first = client.get(f"/api/v1/connections/{demo}/schema", headers=auth).json()
    assert len(first["tables"]) == 8
    cached = client.get(f"/api/v1/connections/{demo}/schema", headers=auth).json()
    assert cached["introspected_at"] == first["introspected_at"]
    refreshed = client.get(f"/api/v1/connections/{demo}/schema?refresh=true", headers=auth).json()
    assert refreshed["introspected_at"] != first["introspected_at"]
    listed = client.get(f"/api/v1/connections/{demo}", headers=auth).json()
    assert listed["table_count"] == 8


def test_changing_connection_settings_clears_the_schema_cache(client, auth, writable_db):
    conn = client.post(
        "/api/v1/connections", headers=auth, json={"name": "Scratch", "db_type": "sqlite", "database": writable_db}
    ).json()
    client.get(f"/api/v1/connections/{conn['id']}/schema", headers=auth)
    assert client.get(f"/api/v1/connections/{conn['id']}", headers=auth).json()["table_count"] == 1
    client.put(f"/api/v1/connections/{conn['id']}", headers=auth, json={"read_only": False})
    assert client.get(f"/api/v1/connections/{conn['id']}", headers=auth).json()["table_count"] is None


def test_schema_errors_are_reported(client, auth):
    conn = client.post(
        "/api/v1/connections",
        headers=auth,
        json={"name": "Down", "db_type": "postgresql", "host": "127.0.0.1", "port": 1, "database": "x"},
    ).json()
    response = client.get(f"/api/v1/connections/{conn['id']}/schema", headers=auth)
    assert response.status_code == 400
    assert response.json()["detail"]
