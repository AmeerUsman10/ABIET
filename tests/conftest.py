"""
Test configuration: an isolated data directory, a scriptable fake language
model, and helpers for common API flows.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_DATA_DIR = tempfile.mkdtemp(prefix="abiet-test-")
os.environ["DATA_DIR"] = _DATA_DIR
os.environ["SECRET_KEY"] = "test-secret-key-for-abiet-tests-only"
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_BASE_URL"] = ""
os.environ.pop("DATABASE_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from ai.llm import get_llm  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.deps import ai_rate_limiter, login_rate_limiter  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import DatabaseConnection, QueryRecord, User  # noqa: E402
from backend.services.connectors import dispose_all  # noqa: E402


class FakeLLM:
    """Returns queued responses in order and records every prompt it receives."""

    def __init__(self):
        self.responses = []
        self.calls = []

    def queue(self, *responses):
        self.responses.extend(responses)
        return self

    def complete_json(self, messages):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("Unexpected LLM call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(messages)
        return response

    @property
    def last_system_prompt(self):
        return self.calls[-1][0]["content"]


@pytest.fixture(scope="session")
def app_client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def fake_llm():
    llm = FakeLLM()
    app.dependency_overrides[get_llm] = lambda: llm
    yield llm
    app.dependency_overrides.pop(get_llm, None)


@pytest.fixture
def client(app_client, fake_llm):
    yield app_client
    with SessionLocal() as db:
        db.execute(delete(QueryRecord))
        db.execute(delete(DatabaseConnection))
        db.execute(delete(User))
        db.commit()
    ai_rate_limiter.reset()
    login_rate_limiter.reset()
    dispose_all()


def register(client, username="alice", password="correct-horse-battery"):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": password},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


@pytest.fixture
def demo(client, auth):
    response = client.post("/api/v1/connections/demo", headers=auth)
    assert response.status_code == 200, response.text
    return response.json()["id"]


@pytest.fixture
def data_dir():
    return Path(_DATA_DIR)
