from conftest import register

from ai.learning.learning_engine import LearningEngine
from backend.database import SessionLocal


def ask(client, auth, conn_id, question, fake_llm, sql, **extra):
    fake_llm.queue({"sql": sql, "explanation": "x"})
    response = client.post(
        "/api/v1/query/ask", headers=auth, json={"connection_id": conn_id, "question": question, **extra}
    )
    assert response.status_code == 200, response.text
    return response.json()["query"]


def feedback(client, auth, query_id, **body):
    response = client.post(f"/api/v1/queries/{query_id}/feedback", headers=auth, json=body)
    assert response.status_code == 200, response.text


def test_approved_and_corrected_queries_become_prompt_examples(client, auth, demo, fake_llm):
    approved = ask(client, auth, demo, "Top 5 customers by revenue", fake_llm, "SELECT company_name FROM customers")
    feedback(client, auth, approved["id"], rating=1)
    wrong = ask(client, auth, demo, "Total revenue in 2025", fake_llm, "SELECT 1 AS revenue")
    corrected_sql = "SELECT SUM(revenue) AS revenue FROM order_revenue WHERE order_date LIKE '2025%'"
    feedback(client, auth, wrong["id"], rating=-1, corrected_sql=corrected_sql)
    unrated = ask(client, auth, demo, "Top 5 products by revenue", fake_llm, "SELECT name FROM products")
    assert unrated["rating"] is None

    ask(client, auth, demo, "Top 10 customers by revenue", fake_llm, "SELECT 1 AS x")
    prompt = fake_llm.last_system_prompt
    assert "previously answered correctly" in prompt
    assert "Question: Top 5 customers by revenue\nSQL: SELECT company_name FROM customers" in prompt
    assert "Top 5 products by revenue" not in prompt  # never approved

    ask(client, auth, demo, "Total revenue for 2025", fake_llm, "SELECT 1 AS x")
    assert f"SQL: {corrected_sql}" in fake_llm.last_system_prompt
    assert "SELECT 1 AS revenue" not in fake_llm.last_system_prompt  # the wrong answer is not taught


def test_examples_do_not_leak_between_connections_or_users(client, auth, demo, fake_llm):
    approved = ask(client, auth, demo, "Top customers by revenue", fake_llm, "SELECT company_name FROM customers")
    feedback(client, auth, approved["id"], rating=1)
    other = register(client, "bob")
    other_demo = client.post("/api/v1/connections/demo", headers=other).json()["id"]
    ask(client, other, other_demo, "Top customers by revenue", fake_llm, "SELECT 1 AS x")
    assert "previously answered correctly" not in fake_llm.last_system_prompt


def test_similar_pattern_ranking_prefers_closer_questions_and_dedupes(client, auth, demo, fake_llm):
    for question, sql in [
        ("monthly revenue in 2025", "SELECT 'old'"),
        ("monthly revenue in 2025", "SELECT 'new'"),
        ("revenue by region", "SELECT 'region'"),
        ("list all employees", "SELECT 'employees'"),
    ]:
        feedback(client, auth, ask(client, auth, demo, question, fake_llm, f"{sql} AS x")["id"], rating=1)
    with SessionLocal() as db:
        examples = LearningEngine(db).find_similar_patterns(demo, "What was monthly revenue in 2025?", limit=5)
    assert [e.question for e in examples][:2] == ["monthly revenue in 2025", "revenue by region"]
    assert examples[0].sql == "SELECT 'new' AS x"  # the newest answer to a repeated question wins
    assert all(e.question != "list all employees" for e in examples)


def test_learned_examples_endpoint(client, auth, demo, fake_llm):
    approved = ask(
        client, auth, demo, "Orders per status", fake_llm, "SELECT status, COUNT(*) AS n FROM orders GROUP BY 1"
    )
    feedback(client, auth, approved["id"], rating=1)
    items = client.get(f"/api/v1/learning/examples?connection_id={demo}", headers=auth).json()
    assert items == [
        {
            "query_id": approved["id"],
            "question": "Orders per status",
            "sql": "SELECT status, COUNT(*) AS n FROM orders GROUP BY 1",
            "source": "approved",
        }
    ]
    feedback(client, auth, approved["id"], rating=0)
    assert client.get(f"/api/v1/learning/examples?connection_id={demo}", headers=auth).json() == []


def test_insights_summarize_accuracy_errors_and_usage(client, auth, demo, fake_llm):
    ok = ask(
        client, auth, demo, "Orders per status", fake_llm, "SELECT status, COUNT(*) AS n FROM orders GROUP BY status"
    )
    feedback(client, auth, ok["id"], rating=1)
    fake_llm.queue({"sql": "SELECT nope FROM orders"}, {"sql": "SELECT nope FROM orders"})
    client.post("/api/v1/query/ask", headers=auth, json={"connection_id": demo, "question": "Broken"})
    bad = ask(
        client,
        auth,
        demo,
        "Customers and their orders",
        fake_llm,
        "SELECT c.company_name, o.order_id FROM customers c JOIN orders o ON o.customer_id = c.customer_id",
    )
    feedback(client, auth, bad["id"], rating=-1, comment="Wrong: should only show 2025")
    ask(client, auth, demo, "Delete everything", fake_llm, "DELETE FROM orders")

    data = client.get("/api/v1/learning/insights?days=7", headers=auth).json()
    totals, fb = data["analysis"]["totals"], data["analysis"]["feedback"]
    assert totals["queries"] == 4 and totals["ai_questions"] == 4
    assert totals["success"] == 2 and totals["errors"] == 1 and totals["blocked"] == 1
    assert totals["success_rate"] == round(2 / 3, 3)
    assert fb["positive"] == 1 and fb["negative"] == 1 and fb["approval_rate"] == 0.5
    assert fb["themes"] == {"incorrect_results": 1}
    assert data["analysis"]["top_errors"][0]["error"].startswith("no such column")
    assert data["analysis"]["query_features"]["join"] == 1
    assert data["analysis"]["query_features"]["aggregate"] == 1
    assert len(data["analysis"]["daily"]) == 7
    assert sum(d["total"] for d in data["analysis"]["daily"]) == 4
    assert data["analysis"]["recent_negative"][0]["question"] == "Customers and their orders"
    assert any("blocked" in s for s in data["suggestions"])


def test_instance_wide_insights_are_admin_only(client, auth, demo):
    other = register(client, "bob")
    assert client.get("/api/v1/learning/insights?scope=all", headers=auth).status_code == 200  # alice is admin
    assert client.get("/api/v1/learning/insights?scope=all", headers=other).status_code == 403
    assert client.get("/api/v1/learning/insights", headers=other).status_code == 200


def test_ai_insights(client, auth, demo, fake_llm):
    fake_llm.queue({"summary": "Things look fine.", "recommendations": ["Rate more answers"]})
    response = client.post("/api/v1/learning/insights/ai", headers=auth)
    assert response.status_code == 200
    assert response.json() == {"summary": "Things look fine.", "recommendations": ["Rate more answers"]}
    assert "natural-language-to-SQL" in fake_llm.calls[-1][0]["content"]
