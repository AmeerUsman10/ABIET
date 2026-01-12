import sys
import pathlib
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@patch('ai.nlp.query_processor.openai.OpenAI')
def test_end_to_end_query_flow(mock_openai_class, client):
    """Integration test for the complete query processing flow."""
    # Mock the OpenAI client and response
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '''{
        "intent": "retrieve customer data",
        "sql": "SELECT * FROM customers WHERE active = 1",
        "entities": {"table": "customers", "condition": "active"}
    }'''
    mock_client.chat.completions.create.return_value = mock_response
    
    # Send query request
    response = client.post("/api/v1/query/process", json={"query": "show me all active customers"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    
    result = data["data"]
    assert result["original"] == "show me all active customers"
    parsed = result["parsed"]
    assert parsed["intent"] == "retrieve customer data"
    assert parsed["sql"] == "SELECT * FROM customers WHERE active = 1"
    assert parsed["entities"] == {"table": "customers", "condition": "active"}

@patch('ai.nlp.query_processor.openai.OpenAI')
def test_end_to_end_query_flow_with_error(mock_openai_class, client):
    """Test end-to-end flow when OpenAI fails."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API unavailable")
    
    response = client.post("/api/v1/query/process", json={"query": "invalid query"})
    
    assert response.status_code == 200  # The endpoint catches exceptions
    data = response.json()
    assert data["status"] == "success"
    
    result = data["data"]
    parsed = result["parsed"]
    assert parsed["intent"] == "error"
    assert parsed["sql"] is None
    assert "API unavailable" in parsed["error"]

def test_query_endpoint_invalid_input(client):
    """Test query endpoint with invalid input."""
    response = client.post("/api/v1/query/process", json={"invalid": "data"})
    
    # Pydantic should validate and reject
    assert response.status_code == 422  # Validation error