# ABIET architecture

ABIET is a single FastAPI application that serves a REST API under `/api/v1` and a dependency-free web UI at `/`.
It keeps its own data (users, saved connections, query history) in an internal database and connects to the
user's databases on demand.

```
Browser (frontend/)                    ABIET server                              User databases
────────────────────        ──────────────────────────────────────        ───────────────────────
 Ask · History · Saved  ──►  backend/routes  (auth, connections,    ──►   SQL Server, PostgreSQL,
 Connections · Insights      query, history, learning, health)            Oracle, MySQL, SQLite
                                  │
                              backend/services
                              ├─ assistant.py   ask/run workflow
                              ├─ connectors.py  URLs, engines, tests, schema introspection
                              ├─ sql_guard.py   read-only safety analysis
                              ├─ executor.py    execution, serialization, CSV
                              └─ demo.py        sample sales database
                                  │
                              ai/
                              ├─ llm.py                     OpenAI-compatible client  ──►  AI provider
                              ├─ nlp/prompts.py             schema rendering, prompts
                              ├─ nlp/query_processor.py     generate / repair
                              ├─ learning/learning_engine.py examples & suggestions
                              └─ feedback_processor.py      insights
                                  │
                              Internal database (SQLite or PostgreSQL, Alembic migrations)
```

## Request flow: asking a question

`POST /api/v1/query/ask` → `backend/services/assistant.py:ask`

1. **Schema.** The connection's schema is loaded from cache or introspected (`connectors.introspect_schema`):
   tables and views, columns and types, primary and foreign keys, column comments, and up to ten distinct values of
   short categorical text columns (sampled from the first 10,000 rows, within a 15-second budget).
2. **Context.** `LearningEngine.find_similar_patterns` retrieves approved or corrected question/SQL pairs for the
   same connection, ranked by word overlap. For follow-ups, earlier turns of the conversation are included.
3. **Prompt.** `ai/nlp/prompts.py` renders the schema compactly. When it exceeds `AI_SCHEMA_CHAR_BUDGET`, tables
   are ranked by relevance to the question (with a boost for tables linked by foreign keys) and the rest are listed
   by name only. Identifiers are quoted per dialect and dialect-specific rules are added (e.g. `TOP` on SQL Server,
   `FETCH FIRST` on Oracle).
4. **Generation.** The model returns JSON: `sql`, `explanation`, optional `clarification`, optional `chart`.
   With no SQL, the question is recorded with status `clarification` and the UI asks the user.
5. **Safety.** `sql_guard.analyze_sql` classifies the statement (see below). Unsafe statements are recorded as
   `blocked` on read-only connections, or `needs_confirmation` on writable ones.
6. **Execution.** `executor.execute_sql` runs the statement with `no_parameters` (so `%` and `::` are passed
   through untouched), streams at most `QUERY_MAX_ROWS + 1` rows and serializes values to JSON.
7. **Repair.** If execution fails for a reason other than connectivity, the failing SQL and the database error are
   sent back to the model (`QueryProcessor.repair`), up to `AI_MAX_REPAIR_ATTEMPTS` times.
8. **Record.** Everything is stored in `query_history`, which drives history, saved queries, feedback, learning
   and insights.

`POST /api/v1/query/run` runs SQL typed or edited by the user through the same safety check and executor. Editing
the SQL of an answer that was approved withdraws the approval, so the learning engine never pairs a question with
SQL the user did not approve.

## SQL safety model

A statement is treated as read-only only when all of these agree:

1. It is a single statement; `;`-separated batches and T-SQL `GO` are rejected outright.
2. [sqlglot](https://github.com/tobymao/sqlglot) parses it in the connection's dialect as a `SELECT` or set
   operation, and no node anywhere in the tree is DML, DDL, `SELECT … INTO`, a command, or a locking clause. This
   catches data-modifying CTEs such as `WITH d AS (DELETE … RETURNING *) SELECT …`.
3. A keyword scan over the statement with comments, string literals and quoted identifiers removed finds no
   write or administrative keywords. This also covers SQL sqlglot cannot parse.
4. No known side-effecting function is called (`pg_terminate_backend`, `pg_sleep`, `dblink`, `DBMS_*`, `UTL_*`,
   `load_file`, `load_extension`, …).

Read-only statements then run in a transaction that is always rolled back, declared `READ ONLY` on PostgreSQL,
MySQL and Oracle; read-only SQLite connections are opened with `mode=ro`. Every query has a time limit
(`statement_timeout` on PostgreSQL, `max_execution_time`/`max_statement_time` on MySQL/MariaDB, driver timeouts on SQL Server and Oracle, a progress handler on SQLite). Results are streamed and reading stops after `QUERY_MAX_ROWS`, so large tables are never transferred in full.

Write statements run only on connections where writes were enabled, and only after the user confirms each one.

## Data model

| Table | Purpose |
|---|---|
| `users` | Accounts: bcrypt password hash, admin flag (the first account), active flag |
| `db_connections` | A user's saved databases: type, host, port, database, username, Fernet-encrypted password, type-specific options, read-only flag, cached schema |
| `query_history` | Every question or statement: generated and executed SQL, explanation, status, error, repaired flag, row count, duration, rating, comment, corrected SQL, saved flag and title, parent (for follow-ups) |

Migrations live in `backend/migrations` and run automatically at startup. The initial migration upgrades an
ABIET 0.1 database in place. A test fails whenever the models and the migrations diverge.

## Security

- **Authentication:** bcrypt password hashes; HS256 JWT bearer tokens (`ACCESS_TOKEN_EXPIRE_MINUTES`); login
  attempts are rate-limited per account.
- **Authorization:** every connection and history lookup checks ownership; other users' records return 404.
  History only follows a connection link when the connection belongs to the same user, and SQLite foreign keys are
  enforced so deleted connections are unlinked rather than dangling.
- **Secrets:** connection passwords are encrypted with a key derived from `SECRET_KEY` and are never returned by
  the API. If `SECRET_KEY` is unset, a random key is generated once and stored in `DATA_DIR/.secret_key` (mode 600).
- **SQLite sandbox:** SQLite connections are limited to files inside `DATA_DIR/databases`, so ABIET's own database
  or arbitrary server files cannot be registered as connections.
- **Web UI:** strict Content Security Policy (no inline scripts or styles), `X-Frame-Options: DENY`, and all dynamic
  text is inserted with `textContent`.
- **AI usage:** per-user rate limit (`AI_RATE_LIMIT_PER_MINUTE`); query results are never sent to the AI provider,
  and columns that look like personal data are never sampled.

## Learning

The learning loop is deliberately transparent and local:

- **Trusted examples** are history records with a 👍 on a successful query, or with corrected SQL.
- For each question, up to `AI_FEW_SHOT_EXAMPLES` of the most similar trusted examples on the same connection are
  added to the prompt (the newest answer wins when a question was asked several times).
- **Suggestions** in the composer come from the user's own successful questions, weighted by approval.
- **Insights** aggregate success, approval and repair rates, errors, query features and feedback themes, and
  suggest concrete improvements. Administrators can view instance-wide insights.
- Users can see exactly what was learned per connection (**Connections → Learned**) and withdraw an example by
  clearing its rating.

## Frontend

`frontend/` is plain ES modules served as static files: no build step.

- `js/app.js`: session, shell and hash router. `js/state.js`: shared state and events. `js/api.js`: REST client.
- `js/views/`: `ask.js` (schema browser, composer, answers), `history.js`, `connections.js`, `insights.js`, `auth.js`.
- `js/chart.js`: SVG line, bar and column charts with hover/keyboard tooltips; `js/dom.js`: DOM helpers.
- `css/app.css`: light and dark themes via CSS custom properties.
