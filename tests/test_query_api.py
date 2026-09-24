import sqlite3

import pytest
from conftest import register

from ai.llm import LLMError
from backend.config import settings

REVENUE_BY_CATEGORY = (
    "SELECT c.name AS category, ROUND(SUM(i.quantity * i.unit_price), 2) AS revenue "
    "FROM order_items i JOIN products p ON p.product_id = i.product_id "
    "JOIN categories c ON c.category_id = p.category_id GROUP BY c.name ORDER BY revenue DESC"
)


def ask(client, auth, conn_id, question, **extra):
    response = client.post(
        "/api/v1/query/ask", headers=auth, json={"connection_id": conn_id, "question": question, **extra}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def writable(client, auth):
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)
    path = settings.sqlite_dir / "writable.sqlite"
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        db.executemany("INSERT INTO items (name) VALUES (?)", [("a",), ("b",)])
    conn = client.post(
        "/api/v1/connections",
        headers=auth,
        json={"name": "Writable", "db_type": "sqlite", "database": path.name, "read_only": False},
    ).json()
    yield conn["id"], path
    path.unlink(missing_ok=True)


def test_ask_generates_runs_and_records_a_query(client, auth, demo, fake_llm):
    fake_llm.queue(
        {
            "sql": REVENUE_BY_CATEGORY + ";",
            "explanation": "Revenue per product category.",
            "chart": {"type": "bar", "x": "category", "y": ["revenue"]},
        }
    )
    body = ask(client, auth, demo, "Revenue by category")
    query, result = body["query"], body["result"]
    assert query["status"] == "success"
    assert query["generated_sql"] == REVENUE_BY_CATEGORY
    assert query["executed_sql"] == REVENUE_BY_CATEGORY
    assert query["explanation"] == "Revenue per product category."
    assert query["connection_name"] == "Demo - Sales"
    assert result["columns"] == ["category", "revenue"]
    assert result["row_count"] == 6 and result["rows"][0][0] == "Laptops"
    assert body["chart"] == {"type": "bar", "x": "category", "y": ["revenue"]}

    prompt = fake_llm.last_system_prompt
    assert "SQLite" in prompt and "strftime" in prompt
    assert "TABLE order_items" in prompt
    assert "status TEXT values: 'Cancelled', 'Delivered'" in prompt
    assert fake_llm.calls[-1][-1] == {"role": "user", "content": "Revenue by category"}

    history = client.get("/api/v1/queries", headers=auth).json()
    assert history["total"] == 1 and history["items"][0]["id"] == query["id"]


def test_clarifying_questions(client, auth, demo, fake_llm):
    fake_llm.queue({"sql": None, "clarification": "Which year do you mean?"})
    body = ask(client, auth, demo, "How did we do?")
    assert body["query"]["status"] == "clarification"
    assert body["clarification"] == "Which year do you mean?"
    assert body["result"] is None


def test_follow_up_questions_include_the_conversation(client, auth, demo, fake_llm):
    fake_llm.queue({"sql": "SELECT COUNT(*) AS n FROM orders", "explanation": "All orders."})
    first = ask(client, auth, demo, "How many orders?")
    fake_llm.queue({"sql": "SELECT COUNT(*) AS n FROM orders WHERE status = 'Cancelled'", "explanation": "Cancelled."})
    second = ask(client, auth, demo, "Only cancelled ones", parent_id=first["query"]["id"])
    assert second["query"]["parent_id"] == first["query"]["id"]
    messages = fake_llm.calls[-1]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[1]["content"] == "How many orders?"
    assert "SELECT COUNT(*) AS n FROM orders" in messages[2]["content"]


def test_follow_up_parent_must_belong_to_the_user(client, auth, demo, fake_llm):
    fake_llm.queue({"sql": "SELECT 1 AS x", "explanation": "x"})
    parent = ask(client, auth, demo, "q")["query"]["id"]
    other = register(client, "mallory")
    other_demo = client.post("/api/v1/connections/demo", headers=other).json()["id"]
    response = client.post(
        "/api/v1/query/ask", headers=other, json={"connection_id": other_demo, "question": "q", "parent_id": parent}
    )
    assert response.status_code == 404


def test_failed_queries_are_repaired_using_the_database_error(client, auth, demo, fake_llm):
    fake_llm.queue(
        {"sql": "SELECT region_name, COUNT(*) AS customers FROM customers GROUP BY region_name", "explanation": "v1"},
        {
            "sql": "SELECT r.name AS region, COUNT(*) AS customers FROM customers c "
            "JOIN regions r ON r.region_id = c.region_id GROUP BY r.name",
            "explanation": "Customers per region.",
        },
    )
    body = ask(client, auth, demo, "Customers per region")
    assert body["query"]["status"] == "success"
    assert body["query"]["repaired"] is True
    assert "region_name" in body["query"]["generated_sql"]
    assert "JOIN regions" in body["query"]["executed_sql"]
    assert body["query"]["explanation"] == "Customers per region."
    repair_prompt = fake_llm.calls[-1][-1]["content"]
    assert "no such column: region_name" in repair_prompt


def test_repair_is_limited(client, auth, demo, fake_llm):
    fake_llm.queue({"sql": "SELECT nope FROM orders"}, {"sql": "SELECT still_nope FROM orders"})
    body = ask(client, auth, demo, "Broken")
    assert body["query"]["status"] == "error"
    assert "still_nope" in body["query"]["error"]
    assert len(fake_llm.calls) == 2  # one generation + AI_MAX_REPAIR_ATTEMPTS repair


def test_writes_are_blocked_on_read_only_connections(client, auth, demo, fake_llm):
    fake_llm.queue({"sql": "DELETE FROM orders WHERE status = 'Cancelled'", "explanation": "Deletes."})
    body = ask(client, auth, demo, "Delete cancelled orders")
    assert body["query"]["status"] == "blocked"
    assert "read-only" in body["query"]["error"]
    assert body["result"] is None
    run = client.post(
        "/api/v1/query/run",
        headers=auth,
        json={"connection_id": demo, "sql": "DROP TABLE orders", "confirm_write": True},
    ).json()
    assert run["query"]["status"] == "blocked"


def test_writes_need_confirmation_on_writable_connections(client, auth, writable, fake_llm):
    conn_id, path = writable
    fake_llm.queue({"sql": "DELETE FROM items WHERE name = 'a'", "explanation": "Deletes item a."})
    body = ask(client, auth, conn_id, "Remove item a")
    assert body["requires_confirmation"] is True
    assert body["query"]["status"] == "needs_confirmation"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2
    confirmed = client.post(
        "/api/v1/query/run",
        headers=auth,
        json={
            "connection_id": conn_id,
            "sql": body["query"]["executed_sql"] or body["query"]["generated_sql"],
            "query_id": body["query"]["id"],
            "confirm_write": True,
        },
    ).json()
    assert confirmed["query"]["status"] == "success"
    assert confirmed["result"]["affected_rows"] == 1
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_the_prompt_says_whether_writes_are_allowed(client, auth, demo, writable, fake_llm):
    conn_id, _ = writable
    fake_llm.queue({"sql": "SELECT 1 AS x"}, {"sql": "SELECT 1 AS x"})
    ask(client, auth, demo, "q")
    assert "This connection is read-only" in fake_llm.last_system_prompt
    ask(client, auth, conn_id, "q")
    assert "explicitly asks to change data" in fake_llm.last_system_prompt


def test_ai_errors_are_recorded(client, auth, demo, fake_llm):
    fake_llm.queue(LLMError("The AI provider's rate limit or quota was reached"))
    body = ask(client, auth, demo, "Anything")
    assert body["query"]["status"] == "error"
    assert "rate limit" in body["query"]["error"]


def test_ai_not_configured_returns_503(client, auth, demo):
    from ai.llm import get_llm
    from backend.main import app

    app.dependency_overrides.pop(get_llm, None)
    response = client.post("/api/v1/query/ask", headers=auth, json={"connection_id": demo, "question": "q"})
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_ai_requests_are_rate_limited(client, auth, demo, fake_llm, monkeypatch):
    monkeypatch.setattr(settings, "AI_RATE_LIMIT_PER_MINUTE", 2)
    fake_llm.queue({"sql": "SELECT 1 AS x"}, {"sql": "SELECT 1 AS x"})
    ask(client, auth, demo, "one")
    ask(client, auth, demo, "two")
    third = client.post("/api/v1/query/ask", headers=auth, json={"connection_id": demo, "question": "three"})
    assert third.status_code == 429
    assert "Retry-After" in third.headers


def test_run_sql_directly(client, auth, demo):
    body = client.post(
        "/api/v1/query/run",
        headers=auth,
        json={"connection_id": demo, "sql": "SELECT name FROM regions WHERE name LIKE 'E%' ORDER BY name"},
    ).json()
    assert body["query"]["status"] == "success"
    assert body["query"]["question"] is None
    assert body["result"]["rows"] == [["Europe"]]


def test_run_rejects_multiple_statements_and_reports_sql_errors(client, auth, demo):
    multi = client.post("/api/v1/query/run", headers=auth, json={"connection_id": demo, "sql": "SELECT 1; SELECT 2"})
    assert multi.status_code == 400
    bad = client.post("/api/v1/query/run", headers=auth, json={"connection_id": demo, "sql": "SELECT x FROM nowhere"})
    assert bad.status_code == 200
    assert bad.json()["query"]["status"] == "error"
    assert "no such table" in bad.json()["query"]["error"]


def test_editing_sql_withdraws_an_earlier_approval(client, auth, demo, fake_llm):
    fake_llm.queue({"sql": REVENUE_BY_CATEGORY, "explanation": "x"})
    query = ask(client, auth, demo, "Revenue by category")["query"]
    client.post(f"/api/v1/queries/{query['id']}/feedback", headers=auth, json={"rating": 1})
    rerun = client.post(
        "/api/v1/query/run",
        headers=auth,
        json={"connection_id": demo, "sql": REVENUE_BY_CATEGORY, "query_id": query["id"]},
    ).json()
    assert rerun["query"]["rating"] == 1  # same SQL: the approval still applies
    edited = client.post(
        "/api/v1/query/run",
        headers=auth,
        json={"connection_id": demo, "sql": "SELECT name FROM categories", "query_id": query["id"]},
    ).json()
    assert edited["query"]["rating"] is None
    assert edited["query"]["executed_sql"] == "SELECT name FROM categories"
    assert edited["query"]["generated_sql"] == REVENUE_BY_CATEGORY


def test_run_updates_only_queries_on_the_same_connection(client, auth, demo, writable, fake_llm):
    conn_id, _ = writable
    fake_llm.queue({"sql": "SELECT 1 AS x"})
    query = ask(client, auth, demo, "q")["query"]
    response = client.post(
        "/api/v1/query/run", headers=auth, json={"connection_id": conn_id, "sql": "SELECT 1", "query_id": query["id"]}
    )
    assert response.status_code == 400


def test_suggestions_come_from_successful_history(client, auth, demo, fake_llm):
    fake_llm.queue(
        {"sql": "SELECT COUNT(*) AS n FROM orders"},
        {"sql": "SELECT COUNT(*) AS n FROM customers"},
        {"sql": "SELECT nope FROM orders"},
        {"sql": "SELECT nope2 FROM orders"},
    )
    ask(client, auth, demo, "How many orders?")
    ask(client, auth, demo, "How many customers?")
    ask(client, auth, demo, "How many broken things?")
    suggestions = client.get(f"/api/v1/query/suggestions?connection_id={demo}&q=how many", headers=auth).json()
    assert set(suggestions) == {"How many orders?", "How many customers?"}
    filtered = client.get(f"/api/v1/query/suggestions?connection_id={demo}&q=custom", headers=auth).json()
    assert filtered == ["How many customers?"]
