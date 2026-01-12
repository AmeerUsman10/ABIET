import sys
import pathlib

sys.path.insert(0, str(pathlib.Path('/usr/projects/ABIET')))
from ai.nlp.query_processor import processor

def test_process_returns_structure():
    query = "select all customers"
    result = processor.process(query)
    assert result["original"] == query
    assert "parsed" in result
    assert "generated_sql" in result
    assert result["generated_sql"] == "SELECT * FROM customers;"

def test_generate_sql_show():
    result = processor.process("show me users")
    assert result["generated_sql"] == "SELECT * FROM users;"

def test_generate_sql_get():
    result = processor.process("get names from customers")
    assert result["generated_sql"] == "SELECT names FROM customers;"

def test_unrecognized_query():
    result = processor.process("do something weird")
    assert "not recognized" in result["generated_sql"]
