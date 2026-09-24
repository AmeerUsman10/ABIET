from conftest import register


def run(client, auth, conn_id, sql, **extra):
    response = client.post("/api/v1/query/run", headers=auth, json={"connection_id": conn_id, "sql": sql, **extra})
    assert response.status_code == 200, response.text
    return response.json()["query"]


def test_history_lists_filters_and_searches(client, auth, demo):
    run(client, auth, demo, "SELECT COUNT(*) AS n FROM orders", question="How many orders?")
    run(client, auth, demo, "SELECT nope FROM orders", question="Broken query")
    run(client, auth, demo, "SELECT name FROM regions")
    everything = client.get("/api/v1/queries", headers=auth).json()
    assert everything["total"] == 3
    assert everything["items"][0]["executed_sql"] == "SELECT name FROM regions"  # newest first
    errors = client.get("/api/v1/queries?status=error", headers=auth).json()
    assert [q["question"] for q in errors["items"]] == ["Broken query"]
    found = client.get("/api/v1/queries?search=ORDERS", headers=auth).json()
    assert found["total"] == 2
    paged = client.get("/api/v1/queries?limit=1&offset=1", headers=auth).json()
    assert paged["total"] == 3 and len(paged["items"]) == 1
    assert client.get("/api/v1/queries?status=weird", headers=auth).status_code == 422


def test_history_is_private(client, auth, demo):
    query = run(client, auth, demo, "SELECT 1 AS x")
    other = register(client, "mallory")
    assert client.get("/api/v1/queries", headers=other).json()["total"] == 0
    for method, path in [
        ("get", f"/api/v1/queries/{query['id']}"),
        ("patch", f"/api/v1/queries/{query['id']}"),
        ("delete", f"/api/v1/queries/{query['id']}"),
        ("post", f"/api/v1/queries/{query['id']}/feedback"),
        ("get", f"/api/v1/queries/{query['id']}/export.csv"),
    ]:
        kwargs = {"json": {"rating": 1}} if method in ("post", "patch") else {}
        assert getattr(client, method)(path, headers=other, **kwargs).status_code == 404, path


def test_saving_and_renaming(client, auth, demo):
    query = run(client, auth, demo, "SELECT COUNT(*) AS n FROM orders", question="Order count")
    saved = client.patch(f"/api/v1/queries/{query['id']}", headers=auth, json={"is_saved": True}).json()
    assert saved["is_saved"] is True and saved["title"] == "Order count"
    renamed = client.patch(f"/api/v1/queries/{query['id']}", headers=auth, json={"title": "Orders (total)"}).json()
    assert renamed["title"] == "Orders (total)"
    listing = client.get("/api/v1/queries?saved=true", headers=auth).json()
    assert [q["id"] for q in listing["items"]] == [query["id"]]


def test_delete_query(client, auth, demo):
    query = run(client, auth, demo, "SELECT 1 AS x")
    assert client.delete(f"/api/v1/queries/{query['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/queries/{query['id']}", headers=auth).status_code == 404


def test_feedback_ratings_comments_and_corrections(client, auth, demo):
    query = run(client, auth, demo, "SELECT COUNT(*) AS n FROM orders", question="How many orders?")
    up = client.post(f"/api/v1/queries/{query['id']}/feedback", headers=auth, json={"rating": 1}).json()
    assert up["rating"] == 1
    down = client.post(
        f"/api/v1/queries/{query['id']}/feedback",
        headers=auth,
        json={
            "rating": -1,
            "comment": "Exclude cancelled orders",
            "corrected_sql": "SELECT COUNT(*) AS n FROM orders WHERE status <> 'Cancelled';",
        },
    ).json()
    assert down["rating"] == -1
    assert down["feedback_comment"] == "Exclude cancelled orders"
    assert down["corrected_sql"] == "SELECT COUNT(*) AS n FROM orders WHERE status <> 'Cancelled'"
    cleared = client.post(f"/api/v1/queries/{query['id']}/feedback", headers=auth, json={"rating": 0}).json()
    assert cleared["rating"] is None
    bad = client.post(
        f"/api/v1/queries/{query['id']}/feedback",
        headers=auth,
        json={"rating": -1, "corrected_sql": "SELECT 1; SELECT 2"},
    )
    assert bad.status_code == 400


def test_csv_export_reruns_the_full_query(client, auth, demo):
    query = run(client, auth, demo, "SELECT order_id, status FROM orders ORDER BY order_id", question="All orders")
    response = client.get(f"/api/v1/queries/{query['id']}/export.csv", headers=auth)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="All-orders-' in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert lines[0] == "order_id,status"
    assert len(lines) == 2601  # every order, not just the 1000-row preview


def test_csv_export_refuses_failed_or_write_queries(client, auth, demo):
    failed = run(client, auth, demo, "SELECT nope FROM orders")
    response = client.get(f"/api/v1/queries/{failed['id']}/export.csv", headers=auth)
    assert response.status_code == 400 and "no such column" in response.json()["detail"]
    blocked = run(client, auth, demo, "DELETE FROM orders")
    assert client.get(f"/api/v1/queries/{blocked['id']}/export.csv", headers=auth).status_code == 400


def test_deleting_a_connection_keeps_history(client, auth, demo):
    query = run(client, auth, demo, "SELECT 1 AS x")
    client.delete(f"/api/v1/connections/{demo}", headers=auth)
    kept = client.get(f"/api/v1/queries/{query['id']}", headers=auth).json()
    assert kept["connection_id"] is None and kept["connection_name"] is None
    assert client.get(f"/api/v1/queries/{query['id']}/export.csv", headers=auth).status_code == 400


def test_history_never_points_at_another_users_connection(client, auth, demo):
    """Regression: a deleted connection's id must not be reused to reach someone else's database."""
    query = run(client, auth, demo, "SELECT name FROM regions", question="Regions")
    client.delete(f"/api/v1/connections/{demo}", headers=auth)
    other = register(client, "mallory")
    client.post("/api/v1/connections/demo", headers=other)  # may receive the freed id in SQLite
    kept = client.get(f"/api/v1/queries/{query['id']}", headers=auth).json()
    assert kept["connection_id"] is None
    assert client.get(f"/api/v1/queries/{query['id']}/export.csv", headers=auth).status_code == 400


def test_deleting_a_user_removes_their_data(client, auth, demo):
    from backend.database import SessionLocal
    from backend.models import DatabaseConnection, QueryRecord, User

    run(client, auth, demo, "SELECT 1 AS x")
    with SessionLocal() as db:
        db.delete(db.query(User).filter_by(username="alice").one())
        db.commit()
        assert db.query(DatabaseConnection).count() == 0
        assert db.query(QueryRecord).count() == 0
