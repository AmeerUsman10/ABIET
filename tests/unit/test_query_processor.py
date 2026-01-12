import sys
import pathlib

# Add project root to PYTHONPATH for imports
project_root = pathlib.Path('/usr/projects/ABIET')
sys.path.insert(0, str(project_root))

from ai.nlp.query_processor import processor

def test_process_returns_structure():
    query = "select all customers"
    result = processor.process(query)
    assert isinstance(result, dict)
    assert result["original"] == query
    parsed = result["parsed"]
    assert isinstance(parsed, dict)
    assert parsed["tokens"] == query.split()
    assert parsed["token_count"] == len(query.split())
