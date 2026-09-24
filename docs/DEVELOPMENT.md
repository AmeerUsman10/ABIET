# Development

## Setup

Python 3.11 or newer.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # optional: OPENAI_API_KEY to ask questions
uvicorn backend.main:app --reload --port 8000
```

On Linux, `pyodbc` needs unixODBC (`sudo apt-get install unixodbc`) even if you never connect to SQL Server.

The UI is plain JavaScript modules in `frontend/`; edit and reload the page, there is no build step.

## Project layout

```
backend/            FastAPI application
  main.py           app, middleware, static UI
  config.py         settings (environment / .env)
  database.py       internal database engine and migrations runner
  models.py         ORM models
  schemas.py        API request/response models
  security.py       passwords, tokens, secret encryption
  deps.py           auth, ownership and rate-limit dependencies
  routes/           REST endpoints
  services/         connectors, SQL guard, executor, ask/run workflow, demo database
  migrations/       Alembic migrations
ai/                 language-model client, prompts, learning engine, feedback analysis
frontend/           web UI
tests/              pytest suite; tests/e2e has the browser test
```

## Tests

```bash
pytest                          # unit + API tests (about 30 seconds)
```

The suite uses an isolated temporary data directory and a scripted fake language model, so it needs no API key or
network access.

**PostgreSQL.** Two opt-in modes use a real server:

```bash
# Integration tests for PostgreSQL connections (introspection, execution, timeouts, read-only transactions)
ABIET_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest

# Run the whole suite with ABIET's internal store on PostgreSQL (the database must exist)
ABIET_TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/abiet_test pytest
```

**MySQL / MariaDB.** Integration tests for MySQL connections (the database must exist):

```bash
ABIET_TEST_MYSQL_URL=mysql+pymysql://root:mysql@127.0.0.1:3306/abiet_it pytest tests/test_mysql.py
```

**Browser end-to-end test.** Drives the real UI in Chromium against a running server whose AI provider is a mock
that returns canned SQL for the demo database:

```bash
npm install --no-save playwright@1.56.1 && npx playwright install chromium
uvicorn --app-dir tests/e2e mock_openai:app --port 8765 &
DATA_DIR=$(mktemp -d) OPENAI_API_KEY=mock OPENAI_BASE_URL=http://127.0.0.1:8765/v1 uvicorn backend.main:app --port 8000 &
node tests/e2e/ui.test.cjs http://127.0.0.1:8000
```

## Lint and format

```bash
ruff check .
ruff format .
```

CI (`.github/workflows/ci.yml`) runs lint, the test suite on Python 3.11–3.13 with SQLite and with PostgreSQL as
the internal store, the PostgreSQL and MySQL integration tests, the browser test, and builds and health-checks the Docker
image.

## Database migrations

Schema changes to ABIET's own database go through Alembic. After changing `backend/models.py`:

```bash
alembic revision --autogenerate -m "describe the change"
# review the generated file in backend/migrations/versions/
alembic upgrade head            # also runs automatically when the app starts
```

`tests/test_app.py::test_models_match_migrations` fails if a model change has no migration.

## Adding a database type

1. Add a `DbType` to `DB_TYPES` in `backend/services/connectors.py` (driver, sqlglot dialect, default port,
   options) and handle it in `build_url`, `_connect_args` and `_install_timeouts`.
2. Add the key to `DbTypeKey` in `backend/schemas.py` and to the database label/rules in `ai/nlp/prompts.py`.
3. Add the driver to `requirements.txt` and tests to `tests/test_connectors.py`.

## Useful endpoints

Interactive API docs are at `/docs`. Health checks: `/api/v1/health` (liveness) and `/api/v1/ready` (checks the
internal database).
