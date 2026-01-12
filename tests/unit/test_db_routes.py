import sys
import pathlib
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime

from backend.main import app
from backend.models import Base, User
from backend.routes.auth import get_db

# Use in-memory SQLite for testing
TEST_DATABASE_URL = "sqlite:///./test.db"

@pytest.fixture
def test_db():
    # Create test database
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    yield TestingSessionLocal()
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test.db"):
        os.unlink("./test.db")

@pytest.fixture
def client(test_db):
    # Override the database dependency
    def override_get_db():
        try:
            yield test_db
        finally:
            test_db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as c:
        yield c

@pytest.fixture
def auth_token(client):
    # Register and login to get token
    client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass"
    })
    
    login_response = client.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "testpass"
    })
    return login_response.json()["access_token"]

@patch('backend.routes.db._get_engine')
def test_execute_query_success(mock_get_engine, client, auth_token):
    # Mock the engine and connection
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.__iter__.return_value = [{"id": 1, "name": "test"}]
    mock_conn.execute.return_value = mock_result
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_get_engine.return_value = mock_engine
    
    response = client.post("/api/v1/db/execute", 
        json={"db_type": "mssql", "query": "SELECT * FROM test"},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["rows"] == [{"id": 1, "name": "test"}]

@patch('backend.routes.db._get_engine')
def test_execute_query_sql_error(mock_get_engine, client, auth_token):
    # Mock the engine to raise SQLAlchemyError
    from sqlalchemy.exc import SQLAlchemyError
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.side_effect = SQLAlchemyError("SQL Error")
    mock_get_engine.return_value = mock_engine
    
    response = client.post("/api/v1/db/execute", 
        json={"db_type": "mssql", "query": "INVALID SQL"},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 500
    assert "database error occurred" in response.json()["detail"]

def test_execute_query_invalid_db_type(client, auth_token):
    response = client.post("/api/v1/db/execute", 
        json={"db_type": "invalid", "query": "SELECT 1"},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 400
    assert "Unsupported db_type" in response.json()["detail"]

def test_execute_query_unauthorized(client):
    response = client.post("/api/v1/db/execute", 
        json={"db_type": "mssql", "query": "SELECT 1"}
    )
    assert response.status_code == 401