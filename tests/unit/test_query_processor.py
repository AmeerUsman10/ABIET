import pytest
from ai.nlp.query_processor import QueryProcessor

def test_query_processor_initialization():
    processor = QueryProcessor()
    assert processor.model_name == 'google/flan-t5-large'
    assert hasattr(processor, 'nlp_pipeline')
