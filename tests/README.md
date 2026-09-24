# ABIET tests

| File | Covers |
|---|---|
| `test_sql_guard.py` | Read-only analysis across dialects: DML/DDL, `SELECT INTO`, data-modifying CTEs, hidden batches, side-effect functions, literals and comments |
| `test_connectors.py` | URL building (SQL Server instances, Windows auth, special-character passwords, Oracle services), SQLite sandbox, connection tests, schema introspection and value sampling |
| `test_executor.py` | Result serialization, row caps, SQL and connection errors, query timeouts, CSV streaming |
| `test_prompts.py` | Tokenizing and similarity, identifier quoting, schema rendering and ranking, prompt contents, model-output parsing |
| `test_auth.py` | Registration, login, tokens, rate limiting, password change, registration policy, authentication on every endpoint |
| `test_connections_api.py` | Connection CRUD, password encryption, isolation between users, tests, demo database, schema cache |
| `test_query_api.py` | Ask flow end to end with a fake model: prompts, follow-ups, clarifications, repair, write blocking and confirmation, AI errors, rate limits, SQL mode, suggestions |
| `test_history_api.py` | History filters and search, saved queries, feedback, CSV export, privacy, deleted connections and users |
| `test_learning.py` | Learned examples in prompts, isolation, ranking, insights and AI insights |
| `test_app.py` | Health endpoints, UI and security headers, migrations (fresh, upgrade from 0.1, models vs migrations) |
| `test_postgres.py` | PostgreSQL integration (runs when `ABIET_TEST_POSTGRES_URL` is set) |
| `test_mysql.py` | MySQL / MariaDB integration (runs when `ABIET_TEST_MYSQL_URL` is set) |
| `e2e/ui.test.cjs` | Browser test of the whole UI against a mock AI provider (`e2e/mock_openai.py`) |

`conftest.py` points ABIET at a temporary data directory, provides a `FakeLLM` that returns queued responses and
records prompts, and cleans the database between tests.

See [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md) for how to run each group.
