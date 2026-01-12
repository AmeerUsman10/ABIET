# Test Structure

## Testing Framework

ABIET uses pytest for testing with the following structure:

- `unit/`: Unit tests for individual components
- `integration/`: Integration tests for service interactions

## Running Tests

To run all tests:
```bash
pytest
```

To run unit tests only:
```bash
pytest tests/unit/
```

To run integration tests only:
```bash
pytest tests/integration/
```

## Test Coverage

### Unit Tests
- `test_query_processor.py`: Tests for the query processing component with OpenAI mocking
- `test_learning_engine.py`: Tests for the learning engine data storage and retrieval
- `test_auth_routes.py`: Tests for authentication endpoints (register, login, me)
- `test_db_routes.py`: Tests for database execution endpoints

### Integration Tests
- `test_query_flow.py`: End-to-end tests for the query processing API flow

## Mocking

- OpenAI API calls are mocked to avoid requiring API keys in tests
- Database connections are mocked or use in-memory SQLite for isolation
- External dependencies are mocked to ensure fast, reliable tests
