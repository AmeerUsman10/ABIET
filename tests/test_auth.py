from conftest import register

from backend.config import settings
from backend.database import SessionLocal
from backend.models import User
from backend.security import create_access_token


def test_register_returns_token_and_first_user_is_admin(client):
    first = client.post(
        "/api/v1/auth/register", json={"username": "alice", "email": "Alice@Example.com", "password": "password-123"}
    )
    assert first.status_code == 201
    body = first.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["is_admin"] is True
    assert body["user"]["email"] == "alice@example.com"

    second = client.post(
        "/api/v1/auth/register", json={"username": "bob", "email": "bob@example.com", "password": "password-123"}
    )
    assert second.json()["user"]["is_admin"] is False


def test_passwords_are_hashed(client):
    register(client, "alice", "password-123")
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="alice").one()
    assert user.hashed_password.startswith("$2") and "password-123" not in user.hashed_password


def test_duplicate_username_and_email_are_rejected(client):
    register(client, "alice")
    dup_name = client.post(
        "/api/v1/auth/register", json={"username": "ALICE", "email": "other@example.com", "password": "password-123"}
    )
    assert dup_name.status_code == 409
    dup_email = client.post(
        "/api/v1/auth/register", json={"username": "other", "email": "alice@example.com", "password": "password-123"}
    )
    assert dup_email.status_code == 409


def test_registration_validation(client):
    short = client.post("/api/v1/auth/register", json={"username": "al", "email": "a@example.com", "password": "x"})
    assert short.status_code == 422
    bad_email = client.post(
        "/api/v1/auth/register", json={"username": "alice", "email": "nope", "password": "password-123"}
    )
    assert bad_email.status_code == 422
    too_long = client.post(
        "/api/v1/auth/register", json={"username": "alice", "email": "a@example.com", "password": "é" * 40}
    )
    assert too_long.status_code == 422


def test_login_with_username_or_email(client):
    register(client, "alice", "password-123")
    by_name = client.post("/api/v1/auth/login", json={"username": "alice", "password": "password-123"})
    assert by_name.status_code == 200
    by_email = client.post("/api/v1/auth/login", json={"username": "ALICE@example.com", "password": "password-123"})
    assert by_email.status_code == 200
    wrong = client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong-password"})
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "Incorrect username or password"
    unknown = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong-password"})
    assert unknown.status_code == 401


def test_login_is_rate_limited(client):
    register(client, "alice", "password-123")
    codes = [
        client.post("/api/v1/auth/login", json={"username": "alice", "password": "bad"}).status_code for _ in range(11)
    ]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_me_requires_a_valid_token(client):
    headers = register(client, "alice")
    assert client.get("/api/v1/auth/me", headers=headers).json()["username"] == "alice"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer dummy"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401


def test_expired_and_foreign_tokens_are_rejected(client):
    register(client, "alice")
    expired = create_access_token(1, "alice", expires_minutes=-1)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    import jwt

    forged = jwt.encode({"sub": "1", "exp": 9999999999}, "a-completely-different-secret-key-value", algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_deactivated_users_are_rejected(client):
    headers = register(client, "alice")
    with SessionLocal() as db:
        db.query(User).filter_by(username="alice").update({"is_active": False})
        db.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_change_password(client):
    headers = register(client, "alice", "password-123")
    wrong = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "nope", "new_password": "new-password-456"},
    )
    assert wrong.status_code == 400
    ok = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "password-123", "new_password": "new-password-456"},
    )
    assert ok.status_code == 204
    relogin = client.post("/api/v1/auth/login", json={"username": "alice", "password": "new-password-456"})
    assert relogin.status_code == 200


def test_registration_can_be_disabled_after_the_first_account(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_REGISTRATION", False)
    register(client, "admin")  # the very first account is always allowed
    blocked = client.post(
        "/api/v1/auth/register", json={"username": "bob", "email": "bob@example.com", "password": "password-123"}
    )
    assert blocked.status_code == 403


def test_every_data_endpoint_requires_authentication(client):
    for method, path in [
        ("get", "/api/v1/connections"),
        ("post", "/api/v1/connections/demo"),
        ("post", "/api/v1/query/ask"),
        ("post", "/api/v1/query/run"),
        ("get", "/api/v1/query/suggestions"),
        ("get", "/api/v1/queries"),
        ("get", "/api/v1/learning/insights"),
        ("get", "/api/v1/learning/examples?connection_id=1"),
    ]:
        response = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
        assert response.status_code == 401, path
