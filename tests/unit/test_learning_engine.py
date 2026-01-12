import sys
import pathlib
import pytest
import json
import os
import tempfile
from unittest.mock import patch

from ai.learning.learning_engine import LearningEngine

@pytest.fixture
def temp_storage():
    # Create a temporary file for testing
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as f:
        f.write('{"patterns": [], "corrections": [], "interactions": [], "usage_stats": {}}')
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)

@pytest.fixture
def learning_engine(temp_storage):
    return LearningEngine(storage_path=temp_storage)

def test_init_loads_existing_data(temp_storage):
    # Test loading existing data
    data = {"patterns": [{"test": "data"}], "corrections": [], "interactions": [], "usage_stats": {}}
    with open(temp_storage, 'w') as f:
        json.dump(data, f)
    
    engine = LearningEngine(storage_path=temp_storage)
    assert engine.learning_data["patterns"] == [{"test": "data"}]

def test_init_creates_default_data():
    # Test with non-existing file
    engine = LearningEngine(storage_path="nonexistent.json")
    assert "patterns" in engine.learning_data
    assert "corrections" in engine.learning_data
    assert "interactions" in engine.learning_data
    assert "usage_stats" in engine.learning_data
    assert engine.learning_data["patterns"] == []
    assert engine.learning_data["corrections"] == []
    assert engine.learning_data["interactions"] == []
    assert engine.learning_data["usage_stats"] == {}

def test_record_query_pattern(learning_engine):
    learning_engine.record_query_pattern("select users", "SELECT * FROM users", True)
    
    patterns = learning_engine.learning_data["patterns"]
    assert len(patterns) == 1
    pattern = patterns[0]
    assert pattern["natural_query"] == "select users"
    assert pattern["generated_sql"] == "SELECT * FROM users"
    assert pattern["success"] == True
    assert "timestamp" in pattern
    assert pattern["usage_count"] == 1

def test_record_correction(learning_engine):
    learning_engine.record_correction("wrong query", "corrected query")
    
    corrections = learning_engine.learning_data["corrections"]
    assert len(corrections) == 1
    correction = corrections[0]
    assert correction["original"] == "wrong query"
    assert correction["corrected"] == "corrected query"
    assert "timestamp" in correction

def test_record_interaction(learning_engine):
    learning_engine.record_interaction("select users", "SELECT * FROM users", True, "good", None)
    
    interactions = learning_engine.learning_data["interactions"]
    assert len(interactions) == 1
    interaction = interactions[0]
    assert interaction["natural_query"] == "select users"
    assert interaction["generated_sql"] == "SELECT * FROM users"
    assert interaction["success"] == True
    assert interaction["feedback"] == "good"
    assert interaction["error"] is None
    assert "timestamp" in interaction

def test_record_interaction_with_error(learning_engine):
    learning_engine.record_interaction("bad query", None, False, None, "SQL error")
    
    interactions = learning_engine.learning_data["interactions"]
    assert len(interactions) == 1
    interaction = interactions[0]
    assert interaction["natural_query"] == "bad query"
    assert interaction["generated_sql"] is None
    assert interaction["success"] == False
    assert interaction["feedback"] is None
    assert interaction["error"] == "SQL error"

def test_add_feedback_to_interaction(learning_engine):
    learning_engine.record_interaction("query", "sql", True)
    learning_engine.add_feedback_to_interaction(0, "feedback added")
    
    interactions = learning_engine.learning_data["interactions"]
    assert interactions[0]["feedback"] == "feedback added"

def test_add_feedback_invalid_index(learning_engine):
    learning_engine.add_feedback_to_interaction(99, "feedback")  # Invalid index
    # Should not crash, just do nothing

def test_get_interactions(learning_engine):
    learning_engine.record_interaction("query1", "sql1", True)
    learning_engine.record_interaction("query2", "sql2", True)
    
    interactions = learning_engine.get_interactions()
    assert len(interactions) == 2
    
    limited = learning_engine.get_interactions(limit=1)
    assert len(limited) == 1
    assert limited[0]["natural_query"] == "query2"  # Last one

def test_find_similar_patterns(learning_engine):
    # Placeholder implementation returns empty list
    result = learning_engine.find_similar_patterns("query")
    assert result == []

def test_get_query_suggestions(learning_engine):
    # Placeholder implementation returns empty list
    result = learning_engine.get_query_suggestions("part")
    assert result == []