import sys
import pathlib
import pytest
from unittest.mock import patch, MagicMock

from ai.nlp.query_processor import QueryProcessor, processor

@pytest.fixture
def query_processor():
    return QueryProcessor()

@patch('ai.nlp.query_processor.openai.OpenAI')
def test_process_returns_structure(mock_openai_class, query_processor):
    # Mock the OpenAI client and response
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"intent": "retrieve data", "sql": "SELECT * FROM users", "entities": {}}'
    mock_client.chat.completions.create.return_value = mock_response
    
    query = "select all customers"
    result = query_processor.process(query)
    
    assert isinstance(result, dict)
    assert result["original"] == query
    parsed = result["parsed"]
    assert isinstance(parsed, dict)
    assert parsed["intent"] == "retrieve data"
    assert parsed["sql"] == "SELECT * FROM users"
    assert parsed["entities"] == {}

@patch('ai.nlp.query_processor.openai.OpenAI')
def test_process_with_openai_error(mock_openai_class, query_processor):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API Error")
    
    query = "select all customers"
    result = query_processor.process(query)
    
    assert result["original"] == query
    parsed = result["parsed"]
    assert parsed["intent"] == "error"
    assert parsed["sql"] is None
    assert "API Error" in parsed["error"]

@patch('ai.nlp.query_processor.openai.OpenAI')
def test_process_with_invalid_json(mock_openai_class, query_processor):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = 'invalid json'
    mock_client.chat.completions.create.return_value = mock_response
    
    query = "select all customers"
    result = query_processor.process(query)
    
    assert result["original"] == query
    parsed = result["parsed"]
    assert parsed["intent"] == "error"
    assert parsed["sql"] is None
    assert "Invalid JSON response" in parsed["error"]

def test_process_invalid_input_type(query_processor):
    with pytest.raises(TypeError, match="query must be a string"):
        query_processor.process(123)

@patch('ai.nlp.query_processor.openai.OpenAI')
@patch('ai.nlp.query_processor.LearningEngine')
def test_process_records_interaction(mock_learning_engine_class, mock_openai_class, query_processor):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"intent": "retrieve data", "sql": "SELECT * FROM users", "entities": {}}'
    mock_client.chat.completions.create.return_value = mock_response
    
    mock_learning_engine = MagicMock()
    mock_learning_engine_class.return_value = mock_learning_engine
    
    query = "select all customers"
    result = query_processor.process(query)
    
    mock_learning_engine.record_interaction.assert_called_once_with(
        natural_query=query,
        generated_sql="SELECT * FROM users",
        success=True,
        error=None
    )
